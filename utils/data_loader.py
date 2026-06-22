"""
Data Loader Module
Handles all data loading operations from Google Sheets (production) or
a local Excel file (development), with caching, error handling, and validation.

Environment
-----------
Set ENVIRONMENT=development in your .env file to read from data/db.xlsx instead
of Google Sheets. Any other value (or no .env) defaults to production mode.

Usage
-----
Call `initialize_data()` ONCE at app startup (in app.py), before any callbacks
are registered. All views/callbacks should then use:
    - load_data_package()   -> DataPackage (disease_stats, database, etc.)
    - load_livestock_stats() -> (livestock_stats, df_2024, df_2025, data_farm, data_amount)
    - refresh_all_data()     -> force a full reload (e.g. from a "Refresh" button)

Data is cached in module-level globals and only reloaded when forced or when
REFRESH_INTERVAL_SECONDS has elapsed since the last load.
"""

import os
import json
import tempfile
import gspread
import pandas as pd
from typing import Tuple, Optional, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import logging
import time
from functools import wraps
import random
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Environment flag ──────────────────────────────────────────────────────────
IS_DEV = os.getenv("ENVIRONMENT", "production").strip().lower() == "development"
logger.info(f"Data loader running in {'DEVELOPMENT' if IS_DEV else 'PRODUCTION'} mode")


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataLoaderConfig:
    """Configuration for data loader."""

    # Google Sheets configuration
    CREDENTIALS_FILE: str = "assets/credentials.json"
    SPREADSHEET_NAME: str = "Disease DB"

    # Worksheet / sheet names (used for both Google Sheets tabs and Excel sheet names)
    DISEASE_STATS_SHEET: str = "disease_stats"
    DATABASE_SHEET: str      = "database"
    DISEASE_CODE_SHEET: str  = "diseases_code"
    GEO_DATA_SHEET: str      = "laos_regions"
    NEWS_DATA_SHEET: str     = "news_data"
    WEATHER_DATA_SHEET: str  = "weather_data"
    LIVESTOCK_STATS_SHEET: str = "livestock_stats"
    YEARLY_NATIONAL_STATS_SHEET: str = "yearly_national_stats"
    FARM_STATS_SHEET: str    = "farm_stats"
    STATS_BY_DISTRICT: str    = "stats_by_district"
    GROUP_FARMING_STATS: str = "group_farming_stats"
    BREEDING_ANIMAL_STATS: str = "breeding_stats"

    # Local Excel file path (development only)
    LOCAL_EXCEL_PATH: str = "data/db.xlsx"

    # Cache settings
    CACHE_TTL: int = 1000  # seconds

    @property
    def ALL_SHEETS(self):
        return [
            self.DISEASE_STATS_SHEET,
            self.DATABASE_SHEET,
            self.DISEASE_CODE_SHEET,
            self.GEO_DATA_SHEET,
            self.NEWS_DATA_SHEET,
            self.WEATHER_DATA_SHEET,
            self.LIVESTOCK_STATS_SHEET,
            self.YEARLY_NATIONAL_STATS_SHEET,
            self.FARM_STATS_SHEET,
            self.STATS_BY_DISTRICT,
            self.GROUP_FARMING_STATS,
            self.BREEDING_ANIMAL_STATS,
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Data Package
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataPackage:
    """Container for all loaded data."""
    disease_stats:   pd.DataFrame
    database:        pd.DataFrame
    disease_codes:   pd.DataFrame
    geo_data:        pd.DataFrame
    news_data:       pd.DataFrame
    weather_data:    pd.DataFrame
    livestock_stats: pd.DataFrame
    loaded_at:       datetime

    def __post_init__(self):
        self._validate_data()

    def _validate_data(self) -> None:
        for field_name, field_value in self.__dict__.items():
            if field_name == "loaded_at":
                continue
            if field_value is None:
                logger.warning(f"{field_name} is None")
            elif isinstance(field_value, pd.DataFrame) and field_value.empty:
                logger.warning(f"{field_name} is empty")

    def get_data_summary(self) -> Dict[str, Any]:
        return {
            "disease_stats_rows":  len(self.disease_stats),
            "database_rows":       len(self.database),
            "disease_codes_count": len(self.disease_codes),
            "geo_data_regions":    len(self.geo_data),
            "news_items":          len(self.news_data),
            "weather_stations":    len(self.weather_data),
            "livestock_stats":     len(self.livestock_stats),
            "loaded_at":           self.loaded_at.strftime("%Y-%m-%d %H:%M:%S"),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """Rate limiter with exponential backoff and jitter for API calls."""

    def __init__(self, max_retries: int = 5, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.last_request_time = 0
        self.min_interval = 1.2  # Slightly more than 1 request per second

    def wait_if_needed(self):
        """Wait if we're making requests too quickly."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed + random.uniform(0, 0.1)
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(self.max_retries):
                try:
                    self.wait_if_needed()
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e)
                    if '429' in error_str and attempt < self.max_retries - 1:
                        delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(
                            f"Rate limit hit. Retrying in {delay:.2f}s... "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(delay)
                        continue
                    raise
            return func(*args, **kwargs)
        return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions & Cache
# ─────────────────────────────────────────────────────────────────────────────

class DataLoadError(Exception):
    """Custom exception for data loading errors."""
    pass


class SimpleCache:
    """Simple in-memory cache with TTL support and warming capability."""

    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._is_warming = False

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time())

    def clear(self) -> None:
        self._cache.clear()

    def is_fresh(self, key: str) -> bool:
        """Check if cache entry exists and is still fresh."""
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        return (time.time() - timestamp) <= self.ttl


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions for data preprocessing
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_livestock_df(df: pd.DataFrame) -> pd.DataFrame:
    """Replace '-', null, and empty values with 0, strip thousands-separator
    commas, then convert to int (except Province)."""
    df = df.replace(['-', '', None], 0)

    for i, col in enumerate(df.columns):
        if col == 'Province':
            continue
        series = df.iloc[:, i]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        series = (
            series.astype(str)
            .str.replace(',', '', regex=False)
            .str.strip()
            .replace({'': '0', 'nan': '0', 'None': '0'})
        )
        df.isetitem(i, pd.to_numeric(series, errors='coerce').fillna(0).astype(int))

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Production loader  (reads from Google Sheets)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleSheetsDataLoader:
    """Loads data from Google Sheets using gspread (production mode)."""

    def __init__(self, config: DataLoaderConfig):
        self.config = config
        self._connection: Optional[gspread.Spreadsheet] = None
        self._cache = SimpleCache(ttl=config.CACHE_TTL)
        self._rate_limiter = RateLimiter(max_retries=5, base_delay=1.0)

    @RateLimiter(max_retries=5, base_delay=1.0)
    def _get_connection(self) -> gspread.Spreadsheet:
        if self._connection is None:
            try:
                creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
                
                creds_dict = json.loads(creds_json)
                
                with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
                    json.dump(creds_dict, f)
                    temp_creds_path = f.name
                
                gc = gspread.service_account(filename=temp_creds_path)
                self._connection = gc.open(self.config.SPREADSHEET_NAME)
                logger.info(f"Google Sheets connection established for '{self.config.SPREADSHEET_NAME}'")
            except FileNotFoundError as e:
                raise DataLoadError(f"Credentials file '{self.config.CREDENTIALS_FILE}' not found: {e}")
            except Exception as e:
                raise DataLoadError(f"Could not connect to Google Sheets: {e}")
        return self._connection

    @RateLimiter(max_retries=5, base_delay=1.0)
    def _read_worksheet(self, worksheet_name: str) -> pd.DataFrame:
        try:
            logger.info(f"Reading worksheet: {worksheet_name}")
            connection = self._get_connection()
            worksheet = connection.worksheet(worksheet_name)
            records = worksheet.get_all_records()
            data = pd.DataFrame(records)
            if data is None or data.empty:
                logger.warning(f"Worksheet '{worksheet_name}' is empty")
                return pd.DataFrame()
            logger.info(f"Successfully read {len(data)} rows from {worksheet_name}")
            return data
        except gspread.exceptions.WorksheetNotFound as e:
            raise DataLoadError(f"Worksheet '{worksheet_name}' not found: {e}")
        except Exception as e:
            raise DataLoadError(f"Failed to read '{worksheet_name}': {e}")

    @RateLimiter(max_retries=5, base_delay=1.0)
    def _read_worksheet_raw(self, worksheet_name: str) -> list:
        """Read raw data from worksheet (all values including headers)."""
        try:
            logger.info(f"Reading raw worksheet data: {worksheet_name}")
            connection = self._get_connection()
            worksheet = connection.worksheet(worksheet_name)
            data = worksheet.get_all_values()
            logger.info(f"Successfully read raw data from {worksheet_name}")
            return data
        except gspread.exceptions.WorksheetNotFound as e:
            raise DataLoadError(f"Worksheet '{worksheet_name}' not found: {e}")
        except Exception as e:
            raise DataLoadError(f"Failed to read raw data from '{worksheet_name}': {e}")

    def load_all_data(self, use_cache: bool = True) -> DataPackage:
        cache_key = "all_data"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Using cached data")
                return cached

        try:
            logger.info("Loading all data from Google Sheets with rate limiting...")

            disease_stats   = self._read_worksheet(self.config.DISEASE_STATS_SHEET)
            database        = self._read_worksheet(self.config.DATABASE_SHEET)
            disease_codes   = self._read_worksheet(self.config.DISEASE_CODE_SHEET)
            geo_data        = self._read_worksheet(self.config.GEO_DATA_SHEET)
            news_data       = self._read_worksheet(self.config.NEWS_DATA_SHEET)
            weather_data    = self._read_worksheet(self.config.WEATHER_DATA_SHEET)
            livestock_stats = self._read_worksheet(self.config.LIVESTOCK_STATS_SHEET)
            

            data_package = DataPackage(
                disease_stats=disease_stats,
                database=database,
                disease_codes=disease_codes,
                geo_data=geo_data,
                news_data=news_data,
                weather_data=weather_data,
                livestock_stats=livestock_stats,
                loaded_at=datetime.now(),
            )

            self._cache.set(cache_key, data_package)
            logger.info("All data loaded successfully with rate limiting")
            return data_package

        except Exception as e:
            raise DataLoadError(f"Failed to load data: {e}")

    def load_livestock_stats_data(
        self, use_cache: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load and preprocess livestock stats with rate limiting."""
        cache_key = "livestock_stats"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Using cached livestock stats data")
                return cached

        try:
            yearly_raw = self._read_worksheet_raw(self.config.YEARLY_NATIONAL_STATS_SHEET)
            farm_raw = self._read_worksheet_raw(self.config.FARM_STATS_SHEET)
            livestock_stats = self._read_worksheet(self.config.LIVESTOCK_STATS_SHEET)
            stats_by_district = self._read_worksheet(self.config.STATS_BY_DISTRICT)
            group_farming_stats = self._read_worksheet_raw(self.config.GROUP_FARMING_STATS)
            breeding_animal_stats = self._read_worksheet_raw(self.config.BREEDING_ANIMAL_STATS)
            breeding_animal_stats = pd.DataFrame(breeding_animal_stats)
            
            def clean_cell(x):
                import re
                if pd.isna(x):
                    return x
                x = str(x)
                x = x.replace('\n', ' ').strip()
                x = re.sub(r'^\s*[/\-:]+\s*', '', x)
                x = re.sub(r'[^\x00-\x7F]+', '', x)
                x = re.sub(r'\s+', ' ', x).strip()
                return x

            breeding_animal_stats = breeding_animal_stats.applymap(clean_cell)
            

            # Process yearly national stats
            if yearly_raw and len(yearly_raw) >= 3:
                header_level_0 = yearly_raw[0]
                header_level_1 = yearly_raw[1]
                data_rows = yearly_raw[2:]

                multi_headers = pd.MultiIndex.from_arrays([header_level_0, header_level_1])
                yearly_df = pd.DataFrame(data_rows, columns=multi_headers)

                province = yearly_df.iloc[:, 0]
                years = [c for c in yearly_df.columns.get_level_values(0).unique() if str(c).isdigit()]

                if len(years) >= 2:
                    df_24 = yearly_df[years[0]].copy()
                    df_25 = yearly_df[years[1]].copy()

                    df_24.insert(0, 'Province', province)
                    df_25.insert(0, 'Province', province)

                    df_24 = preprocess_livestock_df(df_24)
                    df_25 = preprocess_livestock_df(df_25)
                else:
                    df_24, df_25 = pd.DataFrame(), pd.DataFrame()
            else:
                df_24, df_25 = pd.DataFrame(), pd.DataFrame()

            # Process farm stats
            if farm_raw and len(farm_raw) >= 3:

                header_level_0 = farm_raw[0]
                header_level_1 = farm_raw[1]
                data_rows = farm_raw[2:]

                header_level_0 = (
                    pd.Series(header_level_0)
                    .replace('', pd.NA)
                    .ffill()
                    .tolist()
                )

                # Build MultiIndex
                multi_headers = pd.MultiIndex.from_arrays([header_level_0, header_level_1])

                farm_df = pd.DataFrame(data_rows, columns=multi_headers)

                province = farm_df.iloc[:, 0]

                # Extract views
                data_farm = farm_df.xs('Farm', axis=1, level=1)
                data_amount = farm_df.xs('Amount', axis=1, level=1)

                # Reattach Province
                data_farm.insert(0, 'Province', province)
                data_amount.insert(0, 'Province', province)

                # External preprocessing (unchanged)
                data_farm = preprocess_livestock_df(data_farm)
                data_amount = preprocess_livestock_df(data_amount)

            else:
                data_farm, data_amount = pd.DataFrame(), pd.DataFrame()
                
            # Process group farming stats
            if group_farming_stats and len(group_farming_stats) >= 3:

                header_level_0 = group_farming_stats[0]
                header_level_1 = group_farming_stats[1]
                data_rows = group_farming_stats[2:]

                header_level_0 = (
                    pd.Series(header_level_0)
                    .replace('', pd.NA)
                    .ffill()
                    .tolist()
                )
                multi_headers = pd.MultiIndex.from_arrays([header_level_0, header_level_1])
                farming_data_group = pd.DataFrame(data_rows, columns=multi_headers)
                province = farming_data_group.iloc[:, 0]
                # Extract views
                farming_amount_group = farming_data_group.xs('Amount of group', axis=1, level=1)
                farming_amount_animal = farming_data_group.xs('Amount of animal', axis=1, level=1)

                # Reattach Province
                farming_amount_group.insert(0, 'Province', province)
                farming_amount_animal.insert(0, 'Province', province)

                # External preprocessing (unchanged)
                farming_amount_group = preprocess_livestock_df(farming_amount_group)
                farming_amount_animal = preprocess_livestock_df(farming_amount_animal)

            else:
                farming_amount_group, farming_amount_animal = pd.DataFrame(), pd.DataFrame()
                
            #process stats by district
            stats_by_district = preprocess_livestock_df(stats_by_district)
                        
            result = (livestock_stats, df_24, df_25, data_farm, data_amount, stats_by_district, farming_amount_group, farming_amount_animal, breeding_animal_stats)
            self._cache.set(cache_key, result)
            return result

        except Exception as e:
            raise DataLoadError(f"Failed to load livestock stats: {e}")

    def refresh_cache(self) -> None:
        logger.info("Clearing data cache")
        self._cache.clear()

    def warm_up_cache(self) -> None:
        """Pre-load data to warm up the cache during off-peak times."""
        if not self._cache.is_fresh("all_data"):
            logger.info("Warming up data cache...")
            try:
                self.load_all_data(use_cache=False)
                logger.info("Cache warmed up successfully")
            except Exception as e:
                logger.error(f"Failed to warm up cache: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Factory — returns the right loader based on ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────

def _make_loader(config: Optional[DataLoaderConfig] = None):
    cfg = config or DataLoaderConfig()
    if IS_DEV:
        return LocalExcelDataLoader(cfg)
    return GoogleSheetsDataLoader(cfg)


# Singleton loader instance
_data_loader_instance = None


def _get_data_loader(config: Optional[DataLoaderConfig] = None):
    global _data_loader_instance
    if _data_loader_instance is None:
        _data_loader_instance = _make_loader(config)
    return _data_loader_instance


# ─────────────────────────────────────────────────────────────────────────────
# Data Processor
# ─────────────────────────────────────────────────────────────────────────────

class DataProcessor:
    """Processes and transforms loaded data for specific use cases."""

    @staticmethod
    def prepare_overview_data(data_package: DataPackage) -> Tuple[pd.DataFrame, pd.DataFrame]:
        disease_stats = data_package.disease_stats.copy()
        disease_stats.columns = [
            col.replace("(Head)", "").replace("(Head", "").strip().upper()
            for col in disease_stats.columns
        ]
        numeric_columns = [col for col in disease_stats.columns if col != "YEAR"]
        for col in numeric_columns:
            disease_stats[col] = (
                disease_stats[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(r"[^\d.]", "", regex=True)
                .str.strip()
                .replace("", "0")
                .astype(float)
                .astype(int)
            )
        if "YEAR" in disease_stats.columns:
            disease_stats["YEAR"] = disease_stats["YEAR"].astype(int)
        return disease_stats, data_package.weather_data.copy()

    @staticmethod
    def prepare_disease_analysis_data(data_package: DataPackage) -> pd.DataFrame:
        return pd.merge(
            data_package.database,
            data_package.disease_codes,
            on="disease_code",
            how="left",
        )

    @staticmethod
    def prepare_geographical_data(data_package: DataPackage) -> pd.DataFrame:
        return data_package.geo_data.copy()

    @staticmethod
    def prepare_key_diseases_data(data_package: DataPackage) -> pd.DataFrame:
        database = data_package.database.copy()
        geo_data = data_package.geo_data.copy()
        location_col = None
        for col in ["location", "region", "province", "district"]:
            if col in database.columns and col in geo_data.columns:
                location_col = col
                break
        if location_col is None:
            logger.warning("Could not find matching location column for merge")
            return database
        merged = pd.merge(database, geo_data, on=location_col, how="left", suffixes=("", "_geo"))
        logger.info(f"Merged data on '{location_col}': {len(merged)} rows")
        return merged


# ─────────────────────────────────────────────────────────────────────────────
# Global cache — single load point for the whole app
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_DATA: Optional[DataPackage] = None
_GLOBAL_LIVESTOCK: Optional[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]] = None
_LAST_LOAD_TIME: Optional[float] = None
REFRESH_INTERVAL_SECONDS = 12 * 60 * 60  # 12 hours


def initialize_data(force: bool = False) -> DataPackage:
    """
    Load all sheet data (main data package + livestock stats) once and cache
    in module-level globals.

    Call once at app startup (in app.py) before registering callbacks.
    Subsequent calls are no-ops unless `force=True` or
    REFRESH_INTERVAL_SECONDS has elapsed since the last load.
    """
    global _GLOBAL_DATA, _GLOBAL_LIVESTOCK, _LAST_LOAD_TIME

    now = time.time()
    needs_reload = (
        force
        or _GLOBAL_DATA is None
        or _LAST_LOAD_TIME is None
        or (now - _LAST_LOAD_TIME) > REFRESH_INTERVAL_SECONDS
    )

    if needs_reload:
        logger.info(f"Loading full data package (forced={force})")
        loader = _get_data_loader()
        _GLOBAL_DATA = loader.load_all_data(use_cache=False)
        _GLOBAL_LIVESTOCK = loader.load_livestock_stats_data(use_cache=False)
        _LAST_LOAD_TIME = now

    return _GLOBAL_DATA


def load_data_package() -> DataPackage:
    """Return the cached global DataPackage, loading it if not yet initialized."""
    global _GLOBAL_DATA
    if _GLOBAL_DATA is None:
        return initialize_data()
    return _GLOBAL_DATA


def load_livestock_stats() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Return cached livestock statistics.

    Returns:
        Tuple of 5 DataFrames: (livestock_stats, df_2024, df_2025, data_farm, data_amount)
    """
    global _GLOBAL_LIVESTOCK
    if _GLOBAL_LIVESTOCK is None:
        initialize_data()
    return _GLOBAL_LIVESTOCK


def load_overview_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    return DataProcessor.prepare_overview_data(load_data_package())


def load_disease_analysis_data() -> pd.DataFrame:
    return DataProcessor.prepare_disease_analysis_data(load_data_package())


def load_geographical_data() -> pd.DataFrame:
    return DataProcessor.prepare_geographical_data(load_data_package())


def load_key_diseases_data() -> pd.DataFrame:
    return DataProcessor.prepare_key_diseases_data(load_data_package())


def refresh_all_data() -> DataPackage:
    """Force a full reload of all data. Call from a 'Refresh Data' button callback."""
    return initialize_data(force=True)


# ─────────────────────────────────────────────────────────────────────────────
# Write operations (admin panel)
# ─────────────────────────────────────────────────────────────────────────────

def update_disease_stats_worksheet(updated_data: pd.DataFrame) -> bool:
    if IS_DEV:
        logger.warning("[DEV] update_disease_stats_worksheet is a no-op in development mode")
        return True
    try:
        loader = _get_data_loader()
        connection = loader._get_connection()
        worksheet = connection.worksheet(loader.config.DISEASE_STATS_SHEET)
        worksheet.clear()
        data_with_headers = [updated_data.columns.tolist()] + updated_data.values.tolist()
        worksheet.append_rows(data_with_headers)
        logger.info(f"Successfully updated {loader.config.DISEASE_STATS_SHEET}")
        refresh_all_data()
        return True
    except Exception as e:
        logger.error(f"Error updating disease stats worksheet: {e}")
        return False


def add_new_case_to_database(new_case: dict) -> bool:
    if IS_DEV:
        logger.warning("[DEV] add_new_case_to_database is a no-op in development mode")
        return True
    try:
        loader = _get_data_loader()
        connection = loader._get_connection()
        worksheet = connection.worksheet(loader.config.DATABASE_SHEET)
        new_row_values = [new_case.get(col, "") for col in worksheet.row_values(1)]
        worksheet.append_row(new_row_values)
        logger.info(f"Successfully added case to {loader.config.DATABASE_SHEET}")
        refresh_all_data()
        return True
    except Exception as e:
        logger.error(f"Error adding case to database: {e}")
        return False