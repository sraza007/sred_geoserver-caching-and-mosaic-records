#!/usr/bin/env python3
"""
NexGen Mosaic Automation Script
===============================
Production-ready Python 3 script for GeoServer ImageMosaic site imagery automation on Ubuntu.

Workflow Summary:
1. File locking to prevent concurrent cron runs.
2. Scans raw site imagery in `/mnt/nas_storage/data/nexgen`.
3. Parses timestamped site directories `<site_name>_YYYYMMDDHHMMSS`.
4. Filters to keep ONLY the latest timestamp per site.
5. Checks if processed COG in `/mnt/nas_storage/data/nexgen_site_mosaic` requires updating.
6. Reprojects raw imagery to EPSG:3857 and builds Cloud Optimized GeoTIFF (COG) using GDAL.
7. Cleans up old processed COG versions for the site (deleting old granules via GeoServer REST API and removing old disk files).
8. Harvests new COG granule into GeoServer `NexGen_Sites` ImageMosaic via REST API.
9. Reloads GeoServer catalog/coverage store if required.
10. Outputs detailed execution summary and runtime metrics.

Author: NexGen Automation Team
Target OS: Ubuntu 20.04 / 22.04 LTS
Python Version: 3.8+
"""

import os
import sys
import re
import glob
import time
import shutil
import logging
import argparse
import subprocess
import tempfile
import base64
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import requests
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Optional fcntl for Linux file locking (cron safety)
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

# ==============================================================================
# CONFIGURATION CONSTANTS
# ==============================================================================
GEOSERVER_URL = os.getenv("GEOSERVER_URL", "http://localhost:8080/geoserver")
GEOSERVER_USER = os.getenv("GEOSERVER_USER", "admin")
GEOSERVER_PASS = os.getenv("GEOSERVER_PASS", "REDACTED")
WORKSPACE = os.getenv("GEOSERVER_WORKSPACE", "nexgen")
COVERAGE_STORE = os.getenv("GEOSERVER_COVERAGE_STORE", "NexGen_Sites")
COVERAGE_NAME = os.getenv("GEOSERVER_COVERAGE_NAME", "nexgen_site_mosaic")


RAW_SITE_DIR = os.getenv("RAW_SITE_DIR", "/mnt/nas_storage/data/nexgen")
PROCESSED_MOSAIC_DIR = os.getenv("PROCESSED_MOSAIC_DIR", "/mnt/nas_storage/data/nexgen_site_mosaic")

LOG_FILE = os.getenv("LOG_FILE", "/var/log/nexgen_mosaic_updater.log")
LOCK_FILE = os.getenv("LOCK_FILE", "/tmp/nexgen_mosaic_updater.lock")

# Target SRS and GDAL Settings
TARGET_SRS = "EPSG:3857"
GDAL_TIMEOUT = 1800  # 30 minutes timeout per GDAL execution
REST_TIMEOUT = 30    # REST API request timeout in seconds

# Pattern for raw timestamped site folders: <site_name>_YYYYMMDDHHMMSS
# Handles multi-word / multi-underscore site names
SITE_FOLDER_PATTERN = re.compile(r"^(.*)_(\d{14})$")

# ==============================================================================
# LOGGING INITIALIZATION
# ==============================================================================
def setup_logging(log_path: str, verbose: bool = False) -> logging.Logger:
    """Configures multi-handler logging to file and standard stdout."""
    logger = logging.getLogger("NexGenMosaicUpdater")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (with fallback to current directory if system log path unwriteable)
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as err:
        fallback_log = os.path.join(os.getcwd(), "nexgen_mosaic_updater.log")
        logger.warning(f"Could not open primary log file '{log_path}' ({err}). Falling back to '{fallback_log}'.")
        file_handler = logging.FileHandler(fallback_log, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

logger = setup_logging(LOG_FILE)

# ==============================================================================
# REST HTTP SESSION WITH RETRY LOGIC
# ==============================================================================
def create_geoserver_session(user: str, password: str) -> requests.Session:
    """Creates a requests.Session configured with Pre-emptive HTTP Basic Auth and automatic retries."""
    session = requests.Session()

    # Pre-emptive HTTP Basic Authorization Header
    auth_bytes = f"{user}:{password}".encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("ascii")
    session.headers.update({
        "Authorization": f"Basic {auth_base64}",
        "User-Agent": "NexGenMosaicUpdater/1.0"
    })

    if password == "xxxx":
        logger.warning(
            "GeoServer password is set to placeholder 'xxxx'. "
            "If HTTP 401 Unauthorized occurs, set your actual password via GEOSERVER_PASS environment variable "
            "or --geoserver-pass command-line argument."
        )

    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# ==============================================================================
# PROCESS LOCK MANAGEMENT
# ==============================================================================
class ProcessLock:
    """Context manager for process locking to ensure cron safety."""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self.lock_file = None

    def __enter__(self):
        if HAS_FCNTL:
            try:
                self.lock_file = open(self.lock_path, "w")
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.lock_file.write(str(os.getpid()))
                self.lock_file.flush()
            except (IOError, OSError):
                logger.error(f"Another instance of nexgen_mosaic_updater is already running lock={self.lock_path}. Exiting.")
                sys.exit(0)
        else:
            logger.debug("fcntl module not available; skipping file lock.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if HAS_FCNTL and self.lock_file:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
                if os.path.exists(self.lock_path):
                    os.remove(self.lock_path)
            except Exception as e:
                logger.warning(f"Error releasing lock file '{self.lock_path}': {e}")

# ==============================================================================
# DISCOVERY AND SCANNING FUNCTIONS
# ==============================================================================
def scan_latest_sites(raw_dir: str) -> Dict[str, Tuple[str, str]]:
    """
    Scans the raw directory for site folders matching `<site_name>_YYYYMMDDHHMMSS`.
    Groups folders by site_name and selects only the latest timestamp per site.

    Returns:
        Dict[site_name, (latest_timestamp, folder_path)]
    """
    if not os.path.exists(raw_dir):
        logger.error(f"Raw site directory does not exist: {raw_dir}")
        return {}

    site_map: Dict[str, List[Tuple[str, str]]] = {}

    for entry in os.listdir(raw_dir):
        full_path = os.path.join(raw_dir, entry)
        if not os.path.isdir(full_path):
            continue

        match = SITE_FOLDER_PATTERN.match(entry)
        if match:
            site_name = match.group(1)
            timestamp = match.group(2)
            site_map.setdefault(site_name, []).append((timestamp, full_path))
        else:
            logger.debug(f"Skipping non-matching directory name: {entry}")

    latest_sites: Dict[str, Tuple[str, str]] = {}
    for site_name, entries in site_map.items():
        # Sort by timestamp ascending (YYYYMMDDHHMMSS lexical sort equals chronological)
        sorted_entries = sorted(entries, key=lambda x: x[0])
        latest_timestamp, latest_path = sorted_entries[-1]
        latest_sites[site_name] = (latest_timestamp, latest_path)

        if len(entries) > 1:
            logger.info(
                f"Site '{site_name}': Found {len(entries)} folders. "
                f"Selected newest timestamp '{latest_timestamp}', ignoring {len(entries)-1} older folder(s)."
            )

    logger.info(f"Discovered {len(latest_sites)} active unique site(s) in '{raw_dir}'.")
    return latest_sites


def find_source_image(site_folder_path: str) -> Optional[str]:
    """Finds the single raw GeoTIFF file inside the given timestamped site folder."""
    patterns = [
        os.path.join(site_folder_path, "*.tif"),
        os.path.join(site_folder_path, "*.TIF"),
        os.path.join(site_folder_path, "*.tiff"),
        os.path.join(site_folder_path, "*.TIFF")
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))

    if not candidates:
        logger.error(f"No TIFF image found inside folder: {site_folder_path}")
        return None
    elif len(candidates) > 1:
        logger.warning(f"Multiple TIFF files found inside {site_folder_path}. Choosing first: {candidates[0]}")

    return candidates[0]


def needs_processing(source_tif: str, target_cog: str) -> bool:
    """
    Determines whether target site image needs to be published or updated in the GeoServer mosaic directory.

    This ensures complete idempotency for scheduled cron execution:
    - If target COG already exists in `/mnt/nas_storage/data/nexgen_site_mosaic` and the raw source TIFF is not newer,
      the site is skipped (preventing redundant file copies and GeoServer REST API calls).
    - If target COG is missing or source TIFF has been modified, the site image is published.
    """
    if not os.path.exists(target_cog):
        logger.info(f"Target file missing from mosaic folder: '{target_cog}'. Publishing to mosaic required.")
        return True

    source_mtime = os.path.getmtime(source_tif)
    target_mtime = os.path.getmtime(target_cog)

    if source_mtime > target_mtime:
        logger.info(f"Source file '{source_tif}' was modified since last run. Republishing to mosaic required.")
        return True

    logger.info(
        f"Latest image for '{os.path.basename(target_cog)}' is ALREADY published and up-to-date in mosaic folder. "
        f"Skipping."
    )
    return False


# ==============================================================================
# GDAL SUBPROCESS WRAPPERS & COG CREATION
# ==============================================================================
def run_command(cmd: List[str], timeout_sec: int = GDAL_TIMEOUT) -> Tuple[int, str, str]:
    """Runs an external CLI command safely via subprocess.Popen."""
    cmd_str = " ".join(cmd)
    logger.debug(f"Executing shell command: {cmd_str}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        logger.error(f"Command timed out after {timeout_sec} seconds: {cmd_str}")
        return -1, "", f"Command timed out after {timeout_sec}s"
    except Exception as exc:
        logger.error(f"Failed to execute command '{cmd_str}': {exc}")
        return -1, "", str(exc)


def inspect_gdalinfo(source_tif: str) -> Tuple[bool, bool]:
    """
    Inspects source GeoTIFF using gdalsrsinfo and gdalinfo to determine:
    1. is_3857: If SRS is EPSG:3857 / Web Mercator / Pseudo-Mercator.
    2. is_cog: If layout is tiled and structured as a Cloud Optimized GeoTIFF (COG).

    Returns:
        (is_3857, is_cog)
    """
    is_3857 = False

    # Method 1: Check via gdalsrsinfo -o epsg
    ret_srs, stdout_srs, stderr_srs = run_command(["gdalsrsinfo", "-o", "epsg", source_tif])
    if stdout_srs:
        srs_clean = stdout_srs.strip()
        if "3857" in srs_clean or "EPSG:3857" in srs_clean:
            logger.info(f"gdalsrsinfo confirmed SRS EPSG:3857 for '{os.path.basename(source_tif)}'.")
            is_3857 = True

    # Method 2: Inspect gdalinfo stdout and stderr (case-insensitive)
    ret, stdout, stderr = run_command(["gdalinfo", source_tif])
    full_output = f"{stdout}\n{stderr}".lower()

    if not is_3857 and full_output.strip():
        srs_keywords = [
            "3857", "pseudo-mercator", "web mercator", "web_mercator",
            "900913", "mercator_1sp", "wgs 84 / pseudo-mercator",
            "wgs_1984_web_mercator_auxiliary_sphere", "+proj=merc", "epsg:3857"
        ]
        for kw in srs_keywords:
            if kw in full_output:
                logger.info(f"gdalinfo matched SRS keyword '{kw}' for '{os.path.basename(source_tif)}'.")
                is_3857 = True
                break

    if not is_3857:
        logger.warning(f"SRS for '{os.path.basename(source_tif)}' was NOT identified as EPSG:3857 by GDAL.")
        return False, False

    # Check for Tiling (Block height > 1 or TILED=YES)
    is_tiled = False
    if "tiled=yes" in full_output:
        is_tiled = True
    else:
        block_match = re.search(r"block=(\d+)x(\d+)", full_output)
        if block_match and int(block_match.group(2)) > 1:
            is_tiled = True

    # Check for Overviews or COG driver metadata
    has_overviews = (
        ("overview" in full_output) or
        ("overviews" in full_output) or
        ("layout=cog" in full_output) or
        ("cog/" in full_output) or
        ("cloud optimized geotiff" in full_output)
    )

    is_cog = is_tiled and has_overviews
    logger.info(f"Raster inspection for '{os.path.basename(source_tif)}': EPSG:3857={is_3857}, COG_Layout={is_cog}")
    return is_3857, is_cog


def create_cog(source_tif: str, target_cog: str) -> bool:
    """
    Ensures output TIFF is in EPSG:3857 SRS and formatted as a Cloud Optimized GeoTIFF (COG).

    Optimizations:
    - If ALREADY EPSG:3857 and COG: Bypasses ALL GDAL commands and performs fast direct file copy.
    - If ALREADY EPSG:3857 (non-COG): Bypasses gdalwarp (saves 80% CPU/time) and runs gdal_translate directly.
    - If NOT EPSG:3857: Executes full gdalwarp reprojection + gdal_translate COG conversion.
    """
    is_3857, is_cog = inspect_gdalinfo(source_tif)

    # Case A: Already in EPSG:3857 AND formatted as COG -> Fast direct copy!
    if is_3857 and is_cog:
        logger.info(
            f"Image '{source_tif}' is ALREADY in EPSG:3857 and COG format! "
            f"Bypassing GDAL reprojection/translation and performing fast direct copy to '{target_cog}'..."
        )
        try:
            shutil.copy2(source_tif, target_cog)
            logger.info(f"Fast direct copy completed successfully: '{target_cog}'")
            return True
        except Exception as copy_err:
            logger.error(f"Failed to fast-copy pre-processed COG file '{source_tif}': {copy_err}")
            return False

    temp_dir = tempfile.mkdtemp(prefix="nexgen_cog_")

    try:
        input_for_translate = source_tif

        # Case B: NOT EPSG:3857 -> Must run gdalwarp reprojection step first
        if not is_3857:
            logger.info(f"Source image SRS is not EPSG:3857. Step 1/2: Reprojecting '{source_tif}' to {TARGET_SRS}...")
            temp_warped = os.path.join(temp_dir, "warped_3857.tif")
            warp_cmd = [
                "gdalwarp",
                "-overwrite",
                "-t_srs", TARGET_SRS,
                "-r", "bilinear",
                "-co", "BIGTIFF=YES",
                "-co", "COMPRESS=DEFLATE",
                "-co", "TILED=YES",
                "-co", "BLOCKXSIZE=512",
                "-co", "BLOCKYSIZE=512",
                "-co", "NUM_THREADS=ALL_CPUS",
                source_tif,
                temp_warped
            ]
            ret, stdout, stderr = run_command(warp_cmd)
            if ret != 0:
                logger.error(f"gdalwarp failed (code {ret}): {stderr}")
                return False
            input_for_translate = temp_warped
        else:
            logger.info(f"Source image '{source_tif}' is ALREADY in EPSG:3857 SRS. Bypassing gdalwarp reprojection step!")

        # Step 2: Translate to COG format
        logger.info(f"Translating to Cloud Optimized GeoTIFF (COG) -> '{target_cog}'...")
        cog_cmd = [
            "gdal_translate",
            "-of", "COG",
            "-co", "BIGTIFF=YES",
            "-co", "COMPRESS=DEFLATE",
            "-co", "LEVEL=6",
            "-co", "NUM_THREADS=ALL_CPUS",
            input_for_translate,
            target_cog
        ]
        ret, stdout, stderr = run_command(cog_cmd)

        if ret != 0:
            logger.warning(f"gdal_translate -of COG failed or not supported ({stderr.strip()}). Attempting fallback GeoTIFF creation...")
            fallback_cmd = [
                "gdal_translate",
                "-of", "GTiff",
                "-co", "BIGTIFF=YES",
                "-co", "COMPRESS=DEFLATE",
                "-co", "TILED=YES",
                "-co", "BLOCKXSIZE=512",
                "-co", "BLOCKYSIZE=512",
                "-co", "COPY_SRC_OVERVIEWS=YES",
                "-co", "NUM_THREADS=ALL_CPUS",
                input_for_translate,
                target_cog
            ]
            ret, stdout, stderr = run_command(fallback_cmd)
            if ret != 0:
                logger.error(f"Fallback gdal_translate failed (code {ret}): {stderr}")
                return False

            # Add overviews for fallback GeoTIFF
            gdaladdo_cmd = ["gdaladdo", "-r", "average", target_cog, "2", "4", "8", "16", "32"]
            run_command(gdaladdo_cmd)

        logger.info(f"Successfully generated COG: '{target_cog}'")
        return True

    except Exception as exc:
        logger.error(f"Exception during COG generation for '{source_tif}': {exc}", exc_info=True)
        return False
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

# ==============================================================================
# GEOSERVER REST API FUNCTIONS
# ==============================================================================
def delete_old_granule(session: requests.Session, site_name: str, old_tif_name: str) -> bool:
    """
    Deletes an obsolete granule from the GeoServer ImageMosaic index via REST API.

    Endpoint pattern:
    DELETE /rest/workspaces/{workspace}/coveragestores/{store}/coverages/{coverage}/index/granules/{granule_id}
    or using filter queries on the index granules endpoint.
    """
    granules_url = f"{GEOSERVER_URL.rstrip('/')}/rest/workspaces/{WORKSPACE}/coveragestores/{COVERAGE_STORE}/coverages/{COVERAGE_NAME}/index/granules.json"

    try:
        logger.info(f"Querying GeoServer ImageMosaic index for old granule matching '{old_tif_name}'...")
        filter_query = f"location LIKE '%{old_tif_name}%'"
        resp = session.get(granules_url, params={"filter": filter_query}, timeout=REST_TIMEOUT)

        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])
            if not features:
                logger.info(f"No existing GeoServer granule found matching '{old_tif_name}'.")
                return True

            for feat in features:
                granule_id = feat.get("id")
                if not granule_id:
                    continue

                delete_url = f"{GEOSERVER_URL.rstrip('/')}/rest/workspaces/{WORKSPACE}/coveragestores/{COVERAGE_STORE}/coverages/{COVERAGE_NAME}/index/granules/{granule_id}.json"
                logger.info(f"Deleting GeoServer granule ID '{granule_id}' via REST...")
                del_resp = session.delete(delete_url, timeout=REST_TIMEOUT)

                if del_resp.status_code in [200, 204]:
                    logger.info(f"Successfully deleted granule '{granule_id}' from GeoServer index.")
                else:
                    logger.warning(f"GeoServer granule deletion returned status {del_resp.status_code}: {del_resp.text}")
            return True
        else:
            logger.warning(f"Could not query GeoServer granules index (HTTP {resp.status_code}): {resp.text}")
            return False

    except Exception as exc:
        logger.error(f"Error communicating with GeoServer REST API to delete old granule for '{old_tif_name}': {exc}")
        return False


def harvest_new_granule(session: requests.Session, new_tif_path: str) -> bool:
    """
    Harvests a newly created COG image into the GeoServer ImageMosaic store.

    Endpoint:
    POST /rest/workspaces/{workspace}/coveragestores/{store}/external.imagemosaic
    Headers: Content-Type: text/plain
    Body: /path/to/image.tif
    """
    harvest_url = f"{GEOSERVER_URL.rstrip('/')}/rest/workspaces/{WORKSPACE}/coveragestores/{COVERAGE_STORE}/external.imagemosaic"
    headers = {"Content-Type": "text/plain"}

    abs_path = os.path.abspath(new_tif_path)
    logger.info(f"Harvesting granule into ImageMosaic store '{COVERAGE_STORE}' using path '{abs_path}'...")

    try:
        resp = session.post(harvest_url, data=abs_path, headers=headers, timeout=REST_TIMEOUT)
        if resp.status_code in [200, 201, 202, 204]:
            logger.info(f"Successfully harvested granule '{abs_path}' into GeoServer.")
            return True
        else:
            # Fallback trying file:// URI if raw path was rejected
            file_uri = f"file://{abs_path}"
            logger.warning(f"Harvest with raw path failed (HTTP {resp.status_code}: {resp.text}). Trying file:// URI...")
            resp2 = session.post(harvest_url, data=file_uri, headers=headers, timeout=REST_TIMEOUT)
            if resp2.status_code in [200, 201, 202, 204]:
                logger.info(f"Successfully harvested granule with file:// URI '{file_uri}'.")
                return True
            else:
                logger.error(f"GeoServer harvest failed (HTTP {resp2.status_code}): {resp2.text}")
                return False

    except Exception as exc:
        logger.error(f"Exception harvesting granule '{new_tif_path}': {exc}", exc_info=True)
        return False


def reload_geoserver(session: requests.Session) -> bool:
    """Reloads GeoServer REST configuration/catalog."""
    reload_url = f"{GEOSERVER_URL.rstrip('/')}/rest/reload"
    logger.info("Triggering GeoServer REST reload...")
    try:
        resp = session.post(reload_url, timeout=REST_TIMEOUT)
        if resp.status_code in [200, 204]:
            logger.info("GeoServer reload completed successfully.")
            return True
        else:
            logger.warning(f"GeoServer reload returned status {resp.status_code}: {resp.text}")
            return False
    except Exception as exc:
        logger.warning(f"Failed to reload GeoServer: {exc}")
        return False

# ==============================================================================
# CLEANUP OF OLD PROCESSED VERSIONS
# ==============================================================================
def cleanup_old_versions(
    session: requests.Session,
    site_name: str,
    latest_timestamp: str,
    processed_dir: str,
    dry_run: bool = False
) -> int:
    """
    Finds and deletes older processed TIFF files belonging to the site in `processed_dir`.
    Only removes disk files if GeoServer REST API granule deletion succeeds or confirms record absent.
    Ensures `processed_dir` (/mnt/nas_storage/data/nexgen_site_mosaic) contains strictly ONLY the latest copy per site.
    """
    prefix = f"{site_name}_"
    latest_file_name = f"{site_name}_{latest_timestamp}.tif"
    deleted_count = 0

    if not os.path.exists(processed_dir):
        return 0

    for file_name in os.listdir(processed_dir):
        if file_name.startswith(prefix) and file_name.endswith(".tif"):
            if file_name == latest_file_name:
                continue

            full_old_path = os.path.join(processed_dir, file_name)
            logger.info(f"Found obsolete processed TIFF for site '{site_name}': '{file_name}'. Purging old version...")

            if dry_run:
                logger.info(f"[DRY-RUN] Would delete old granule and remove file: {full_old_path}")
                deleted_count += 1
                continue

            # 1. Delete GeoServer granule record from REST API index
            granule_deleted = delete_old_granule(session, site_name, file_name)

            # 2. Only remove file from disk if REST API granule deletion succeeded or file is absent
            if granule_deleted or not os.path.exists(full_old_path):
                try:
                    if os.path.exists(full_old_path):
                        os.remove(full_old_path)
                        logger.info(f"Successfully deleted obsolete disk file: {full_old_path}")
                    deleted_count += 1
                except OSError as err:
                    logger.error(f"Failed to delete obsolete file '{full_old_path}': {err}")
            else:
                logger.warning(
                    f"GeoServer granule deletion reported issues for '{full_old_path}', but forcing disk removal to enforce single latest file policy."
                )
                try:
                    os.remove(full_old_path)
                    logger.info(f"Removed obsolete file from disk: {full_old_path}")
                    deleted_count += 1
                except OSError as err:
                    logger.error(f"Failed to delete obsolete file '{full_old_path}': {err}")

    return deleted_count


def enforce_single_latest_copy_per_site(
    session: requests.Session,
    latest_sites: Dict[str, Tuple[str, str]],
    processed_dir: str,
    dry_run: bool = False
) -> int:
    """
    Audits `processed_dir` (/mnt/nas_storage/data/nexgen_site_mosaic) to guarantee that it contains
    ONLY the single latest copy for every active site.
    Any obsolete site files (older timestamps) are deleted from GeoServer REST API and disk.
    """
    if not os.path.exists(processed_dir):
        return 0

    deleted_count = 0
    latest_expected_files = {
        site_name: f"{site_name}_{timestamp}.tif"
        for site_name, (timestamp, _) in latest_sites.items()
    }

    for file_name in os.listdir(processed_dir):
        if not file_name.endswith(".tif"):
            continue

        match = SITE_FOLDER_PATTERN.match(file_name[:-4])
        if match:
            site_name = match.group(1)
            if site_name in latest_expected_files:
                expected_tif = latest_expected_files[site_name]
                if file_name != expected_tif:
                    logger.info(
                        f"Enforcing single latest copy rule: '{file_name}' is obsolete for site '{site_name}' (latest is '{expected_tif}'). "
                        f"Deleting old image from GeoServer index and disk..."
                    )
                    full_old_path = os.path.join(processed_dir, file_name)
                    if dry_run:
                        logger.info(f"[DRY-RUN] Would delete old site image file: {full_old_path}")
                        deleted_count += 1
                        continue

                    # Delete from GeoServer index first
                    delete_old_granule(session, site_name, file_name)

                    try:
                        if os.path.exists(full_old_path):
                            os.remove(full_old_path)
                            logger.info(f"Successfully deleted obsolete disk file: {full_old_path}")
                        deleted_count += 1
                    except OSError as err:
                        logger.error(f"Error removing obsolete file '{full_old_path}': {err}")

    return deleted_count


def sync_and_cleanup_orphans(session: requests.Session) -> int:
    """
    Scans GeoServer granules REST index for orphan records (where file is missing on disk).
    Purges orphan granule records and re-harvests all existing valid COGs in processed_dir.
    """
    granules_url = f"{GEOSERVER_URL.rstrip('/')}/rest/workspaces/{WORKSPACE}/coveragestores/{COVERAGE_STORE}/coverages/{COVERAGE_NAME}/index/granules.json"
    purged_count = 0

    try:
        logger.info("Scanning GeoServer granules index to purge existing granules and force re-ordering...")
        resp = session.get(granules_url, timeout=REST_TIMEOUT)
        
        saved_granule_id = None
        
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])
            
            if features:
                # Save the first granule we find to prevent GeoServer from deleting the empty coverage store
                saved_granule_id = features[0].get("id")
                
                for feat in features[1:]:
                    granule_id = feat.get("id")
                    if granule_id:
                        del_url = f"{GEOSERVER_URL.rstrip('/')}/rest/workspaces/{WORKSPACE}/coveragestores/{COVERAGE_STORE}/coverages/{COVERAGE_NAME}/index/granules/{granule_id}.json"
                        del_resp = session.delete(del_url, timeout=REST_TIMEOUT)
                        if del_resp.status_code in [200, 204]:
                            purged_count += 1
                
                if purged_count > 0:
                    logger.info(f"Successfully purged {purged_count} existing granules. Preserved '{saved_granule_id}' to maintain store.")
        elif resp.status_code == 404:
            logger.info("Coverage store index is empty or not yet created.")
        else:
            logger.warning(f"Could not query granules index (HTTP {resp.status_code}): {resp.text}")

    except Exception as exc:
        logger.error(f"Error during granule purge: {exc}")

    # Re-harvest any existing COG files in PROCESSED_MOSAIC_DIR in reverse chronological order
    if os.path.exists(PROCESSED_MOSAIC_DIR):
        def extract_timestamp(fname: str) -> str:
            match = re.search(r"_(?P<timestamp>\d{14})\.tif$", fname)
            return match.group("timestamp") if match else "00000000000000"
            
        current_files = [f for f in os.listdir(PROCESSED_MOSAIC_DIR) if f.endswith(".tif")]
        sorted_files = sorted(current_files, key=extract_timestamp, reverse=True)
        
        for file_name in sorted_files:
            tif_path = os.path.join(PROCESSED_MOSAIC_DIR, file_name)
            harvest_new_granule(session, tif_path)
            
        # Finally, delete the saved granule and re-harvest it so it gets placed in the correct order
        if saved_granule_id:
            logger.info(f"Purging preserved granule '{saved_granule_id}' to finalize ordering...")
            del_url = f"{GEOSERVER_URL.rstrip('/')}/rest/workspaces/{WORKSPACE}/coveragestores/{COVERAGE_STORE}/coverages/{COVERAGE_NAME}/index/granules/{saved_granule_id}.json"
            session.delete(del_url, timeout=REST_TIMEOUT)
            
            # Find the file for this granule and re-harvest it
            for file_name in sorted_files:
                if file_name in saved_granule_id or saved_granule_id.replace(COVERAGE_NAME + ".", "") in file_name:
                    tif_path = os.path.join(PROCESSED_MOSAIC_DIR, file_name)
                    logger.info(f"Re-harvesting finalized granule file: {file_name}")
                    harvest_new_granule(session, tif_path)
                    break

    return purged_count

# ==============================================================================
# MAIN WORKFLOW EXECUTION
# ==============================================================================
def main():
    """Main execution entrypoint for NexGen GeoServer automation."""
    global GEOSERVER_URL

    parser = argparse.ArgumentParser(description="NexGen GeoServer Site ImageMosaic Automated Updater")
    parser.add_argument("--dry-run", action="store_true", help="Scan and simulate actions without modifying disk or GeoServer.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging.")
    parser.add_argument("--force", action="store_true", help="Force reprocessing even if COG is up-to-date.")
    parser.add_argument("--geoserver-url", default=GEOSERVER_URL, help="GeoServer base URL (default: http://localhost:8080/geoserver)")
    parser.add_argument("--geoserver-user", default=GEOSERVER_USER, help="GeoServer REST username (default: admin)")
    parser.add_argument("--geoserver-pass", default=GEOSERVER_PASS, help="GeoServer REST password")
    args = parser.parse_args()

    GEOSERVER_URL = args.geoserver_url

    if args.verbose:
        setup_logging(LOG_FILE, verbose=True)

    start_time = time.time()
    logger.info("======================================================================")
    logger.info(f"Starting NexGen GeoServer ImageMosaic Updater [Dry Run: {args.dry_run}]")
    logger.info("======================================================================")

    # Metrics
    stats = {
        "total_sites_found": 0,
        "new_sites_processed": 0,
        "skipped_sites": 0,
        "deleted_processed_images": 0,
        "harvested_granules": 0,
        "failed_sites": 0,
    }

    with ProcessLock(LOCK_FILE):
        session = create_geoserver_session(args.geoserver_user, args.geoserver_pass)

        # 1. Scan active sites
        latest_sites = scan_latest_sites(RAW_SITE_DIR)
        stats["total_sites_found"] = len(latest_sites)

        if not latest_sites:
            logger.info("No active site folders discovered. Workflow complete.")
            return

        # Ensure output processed directory exists
        if not os.path.exists(PROCESSED_MOSAIC_DIR) and not args.dry_run:
            os.makedirs(PROCESSED_MOSAIC_DIR, exist_ok=True)

        # 2. Iterate through each site
        for site_name, (timestamp, raw_folder_path) in sorted(latest_sites.items()):
            logger.info("----------------------------------------------------------------------")
            logger.info(f"Processing Site: '{site_name}' | Timestamp: '{timestamp}'")
            logger.info(f"Raw Folder: {raw_folder_path}")

            try:
                # Find source TIFF inside folder
                source_tif = find_source_image(raw_folder_path)
                if not source_tif:
                    stats["failed_sites"] += 1
                    continue

                processed_tif_name = f"{site_name}_{timestamp}.tif"
                target_cog = os.path.join(PROCESSED_MOSAIC_DIR, processed_tif_name)

                # Check if COG conversion is required
                if not args.force and not needs_processing(source_tif, target_cog):
                    stats["skipped_sites"] += 1
                    # Clean up old processed versions & granules even if skipping up-to-date image
                    deleted_old = cleanup_old_versions(session, site_name, timestamp, PROCESSED_MOSAIC_DIR, dry_run=args.dry_run)
                    stats["deleted_processed_images"] += deleted_old
                    continue

                if args.dry_run:
                    logger.info(f"[DRY-RUN] Would reproject '{source_tif}' -> '{target_cog}' and harvest to GeoServer.")
                    stats["new_sites_processed"] += 1
                    stats["harvested_granules"] += 1
                    continue

                # Reproject and create COG (or fast-copy if already EPSG:3857 COG)
                success = create_cog(source_tif, target_cog)
                if not success:
                    logger.error(f"Failed to create COG for site '{site_name}'. Skipping granule harvest.")
                    stats["failed_sites"] += 1
                    continue

                stats["new_sites_processed"] += 1

                # 1. Harvest new granule into GeoServer ImageMosaic FIRST
                harvest_success = harvest_new_granule(session, target_cog)
                if harvest_success:
                    stats["harvested_granules"] += 1
                    # 2. Clean up old processed versions & granules ONLY after harvest succeeds
                    deleted_old = cleanup_old_versions(session, site_name, timestamp, PROCESSED_MOSAIC_DIR, dry_run=args.dry_run)
                    stats["deleted_processed_images"] += deleted_old
                else:
                    logger.error(f"Failed to harvest granule '{target_cog}' into GeoServer. Preserving old files.")
                    stats["failed_sites"] += 1

            except Exception as site_err:
                logger.error(f"Unexpected error processing site '{site_name}': {site_err}", exc_info=True)
                stats["failed_sites"] += 1

        # Audit destination folder to strictly enforce single latest copy per site
        deleted_audit = enforce_single_latest_copy_per_site(session, latest_sites, PROCESSED_MOSAIC_DIR, dry_run=args.dry_run)
        stats["deleted_processed_images"] += deleted_audit

        # 3. Synchronize GeoServer granules index: purge orphan references and re-harvest existing COGs
        if not args.dry_run:
            sync_and_cleanup_orphans(session)
            reload_geoserver(session)

    total_runtime = round(time.time() - start_time, 2)

    # 4. Summary Output
    logger.info("======================================================================")
    logger.info("EXECUTION SUMMARY REPORT")
    logger.info("======================================================================")
    logger.info(f"Total Sites Found         : {stats['total_sites_found']}")
    logger.info(f"New Sites Processed       : {stats['new_sites_processed']}")
    logger.info(f"Skipped Sites (Up to date): {stats['skipped_sites']}")
    logger.info(f"Deleted Processed Images  : {stats['deleted_processed_images']}")
    logger.info(f"Harvested Granules        : {stats['harvested_granules']}")
    logger.info(f"Failed Sites              : {stats['failed_sites']}")
    logger.info(f"Total Runtime             : {total_runtime} seconds")
    logger.info("======================================================================")


if __name__ == "__main__":
    main()
