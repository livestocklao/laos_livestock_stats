"""
Data Loader Module (Optimized)
Handles all data loading operations from Google Sheets (production) with caching, 
parallel execution, error handling, and validation.

Environment
-----------
Set ENVIRONMENT=development in your .env file to read from data/db.xlsx instead
of Google Sheets. Any other value (or no .env) defaults to production mode.

Usage
-----
Call `initialize_data()` ONCE at app startup (in app.py), before any callbacks
are registered. All views/callbacks should then use:
    - load_data_package()   -> DataPackage (disease_stats, database, etc.)
    - load_livestock_stats() -> Tuple of 9 DataFrames
    - refresh_all_data()     -> force a full reload (e.g. from a "Refresh" button)

Data is cached in module-level globals and only reloaded when forced or when
REFRESH_INTERVAL_SECONDS has elapsed since the last load.
"""

import os
import json
import tempfile
import gspread
import pandas as pd
from typing import Tuple, Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
import logging
import time
from functools import wraps, lru_cache
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import weakref
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
    DATABASE_SHEET: str = "database"
    DISEASE_CODE_SHEET: str = "diseases_code"
    GEO_DATA_SHEET: str = "laos_regions"
    NEWS_DATA_SHEET: str = "news_data"
    WEATHER_DATA_SHEET: str = "weather_data"
    LIVESTOCK_STATS_SHEET: str = "livestock_stats"
    YEARLY_NATIONAL_STATS_SHEET: str = "yearly_national_stats"
    FARM_STATS_SHEET: str = "farm_stats"
    STATS_BY_DISTRICT: str = "stats_by_district"
    GROUP_FARMING_STATS: str = "group_farming_stats"
    BREEDING_ANIMAL_STATS: str = "breeding_stats"

    # Local Excel file path (development only)
    LOCAL_EXCEL_PATH: str = "data/db.xlsx"

    # Cache settings
    CACHE_TTL: int = 1000  # seconds
    
    # Parallel loading settings
    MAX_WORKERS: int = 4  # Limit parallel connections to avoid rate limiting
    CHUNK_SIZE: int = 1000  # For large sheet reading

    @property
    def ALL_SHEETS(self) -> List[str]:
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
    
    @property
    def MAIN_SHEETS(self) -> Dict[str, str]:
        """Sheets loaded in parallel for the main data package."""
        return {
            'disease_stats': self.DISEASE_STATS_SHEET,
            'database': self.DATABASE_SHEET,
            'disease_codes': self.DISEASE_CODE_SHEET,
            'geo_data': self.GEO_DATA_SHEET,
            'news_data': self.NEWS_DATA_SHEET,
            'weather_data': self.WEATHER_DATA_SHEET,
            'livestock_stats': self.LIVESTOCK_STATS_SHEET,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Data Package
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataPackage:
    """Container for all loaded data."""
    disease_stats: pd.DataFrame
    database: pd.DataFrame
    disease_codes: pd.DataFrame
    geo_data: pd.DataFrame
    news_data: pd.DataFrame
    weather_data: pd.DataFrame
    livestock_stats: pd.DataFrame
    loaded_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self._validate_data()

    def _validate_data(self) -> None:
        """Validate data integrity after loading."""
        for field_name, field_value in self.__dict__.items():
            if field_name == "loaded_at":
                continue
            if field_value is None:
                logger.warning(f"{field_name} is None")
            elif isinstance(field_value, pd.DataFrame) and field_value.empty:
                logger.warning(f"{field_name} is empty")

    def get_data_summary(self) -> Dict[str, Any]:
        """Get summary statistics of the data package."""
        return {
            "disease_stats_rows": len(self.disease_stats),
            "database_rows": len(self.database),
            "disease_codes_count": len(self.disease_codes),
            "geo_data_regions": len(self.geo_data),
            "news_items": len(self.news_data),
            "weather_stations": len(self.weather_data),
            "livestock_stats": len(self.livestock_stats),
            "loaded_at": self.loaded_at.strftime("%Y-%m-%d %H:%M:%S"),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter (Enhanced)
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """Enhanced rate limiter with adaptive backoff and connection tracking."""

    def __init__(self, max_retries: int = 5, base_delay: float = 1.0, 
                 min_interval: float = 1.2):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_request_time = 0
        self._consecutive_429 = 0

    def wait_if_needed(self):
        """Wait if we're making requests too quickly."""
        with self._lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.min_interval:
                # Add extra delay if we've been hitting rate limits
                extra_delay = 0.5 * self._consecutive_429
                sleep_time = self.min_interval - elapsed + random.uniform(0, 0.1) + extra_delay
                time.sleep(sleep_time)
            self._last_request_time = time.time()

    def record_rate_limit(self):
        """Record a rate limit hit for adaptive backoff."""
        with self._lock:
            self._consecutive_429 += 1
            # Increase min_interval temporarily
            self.min_interval *= 1.5

    def record_success(self):
        """Record successful request to gradually reduce backoff."""
        with self._lock:
            self._consecutive_429 = max(0, self._consecutive_429 - 1)
            # Gradually return to normal interval
            self.min_interval = max(1.2, self.min_interval * 0.9)

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(self.max_retries):
                try:
                    self.wait_if_needed()
                    result = func(*args, **kwargs)
                    self.record_success()
                    return result
                except Exception as e:
                    error_str = str(e)
                    if '429' in error_str and attempt < self.max_retries - 1:
                        self.record_rate_limit()
                        delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(
                            f"Rate limit hit. Retrying in {delay:.2f}s... "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(delay)
                        last_exception = e
                        continue
                    raise
            # If we've exhausted retries, raise the last exception
            if last_exception:
                raise last_exception
            return func(*args, **kwargs)
        return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions & Cache
# ─────────────────────────────────────────────────────────────────────────────

class DataLoadError(Exception):
    """Custom exception for data loading errors."""
    pass


class SimpleCache:
    """Enhanced in-memory cache with TTL support and statistics."""

    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            value, timestamp = self._cache[key]
            if time.time() - timestamp > self.ttl:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = (value, time.time())

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def clear_key(self, key: str) -> None:
        """Clear a specific cache key."""
        with self._lock:
            self._cache.pop(key, None)

    def is_fresh(self, key: str) -> bool:
        """Check if cache entry exists and is still fresh."""
        with self._lock:
            if key not in self._cache:
                return False
            _, timestamp = self._cache[key]
            return (time.time() - timestamp) <= self.ttl

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1f}%"
            }


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions for data preprocessing (Optimized)
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_livestock_df(df: pd.DataFrame) -> pd.DataFrame:
    """Optimized: Replace '-', null, and empty values with 0, strip thousands-separator
    commas, then convert to int (except Province)."""
    # Create a copy to avoid SettingWithCopyWarning
    df = df.copy()
    
    # Replace all at once instead of column by column
    df.replace(['-', '', None, 'nan', 'None'], 0, inplace=True)
    
    # Process all non-Province columns using vectorized operations
    non_province_cols = [col for col in df.columns if col != 'Province']
    
    if non_province_cols:
        for col in non_province_cols:
            # Convert to string, remove commas, and convert to numeric
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '', regex=False),
                errors='coerce'
            ).fillna(0).astype(int)
    
    return df


def clean_cell_value(x):
    """Clean cell value for special character handling."""
    import re
    if pd.isna(x):
        return x
    x = str(x)
    x = x.replace('\n', ' ').strip()
    x = re.sub(r'^\s*[/\-:]+\s*', '', x)
    x = re.sub(r'[^\x00-\x7F]+', '', x)
    x = re.sub(r'\s+', ' ', x).strip()
    return x


def create_multiindex_dataframe(raw_data: list) -> pd.DataFrame:
    """Create a MultiIndex DataFrame from raw sheet data with headers."""
    if not raw_data or len(raw_data) < 3:
        return pd.DataFrame()
    
    header_level_0 = raw_data[0]
    header_level_1 = raw_data[1]
    data_rows = raw_data[2:]
    
    # Forward fill top-level headers
    header_level_0 = (
        pd.Series(header_level_0)
        .replace('', pd.NA)
        .ffill()
        .tolist()
    )
    
    multi_headers = pd.MultiIndex.from_arrays([header_level_0, header_level_1])
    return pd.DataFrame(data_rows, columns=multi_headers)


# ─────────────────────────────────────────────────────────────────────────────
# Production loader - Google Sheets (Optimized)
# ─────────────────────────────────────────────────────────────────────────────

class GoogleSheetsDataLoader:
    """Optimized data loader for Google Sheets with parallel loading and connection pooling."""

    # Class-level connection cache using weak references
    _connection_pool = weakref.WeakValueDictionary()
    _connection_lock = threading.Lock()

    def __init__(self, config: DataLoaderConfig):
        self.config = config
        self._cache = SimpleCache(ttl=config.CACHE_TTL)
        self._rate_limiter = RateLimiter(max_retries=5, base_delay=1.0)
        self._last_modified_times: Dict[str, str] = {}
        
    def _create_connection(self) -> gspread.Spreadsheet:
        """Create a new Google Sheets connection."""
        try:
            creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
            if not creds_json:
                # Fallback to file-based credentials
                if os.path.exists(self.config.CREDENTIALS_FILE):
                    gc = gspread.service_account(filename=self.config.CREDENTIALS_FILE)
                else:
                    raise DataLoadError(
                        f"Neither GOOGLE_CREDENTIALS_JSON env var nor "
                        f"'{self.config.CREDENTIALS_FILE}' file found"
                    )
            else:
                creds_dict = json.loads(creds_json)
                
                with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
                    json.dump(creds_dict, f)
                    temp_creds_path = f.name
                
                gc = gspread.service_account(filename=temp_creds_path)
                
                # Clean up temp file
                try:
                    os.unlink(temp_creds_path)
                except:
                    pass
            
            return gc.open(self.config.SPREADSHEET_NAME)
        except Exception as e:
            raise DataLoadError(f"Could not connect to Google Sheets: {e}")

    def _get_connection(self) -> gspread.Spreadsheet:
        """Get or create a Google Sheets connection with pooling."""
        creds_key = os.environ.get("GOOGLE_CREDENTIALS_JSON", 
                                    self.config.CREDENTIALS_FILE)[:50]
        
        with self._connection_lock:
            # Check existing pool
            if creds_key in self._connection_pool:
                try:
                    conn = self._connection_pool[creds_key]
                    # Test connection is still valid
                    conn.sheet1
                    return conn
                except:
                    # Connection is stale, remove it
                    del self._connection_pool[creds_key]
            
            # Create new connection
            conn = self._create_connection()
            self._connection_pool[creds_key] = conn
            logger.info(f"Google Sheets connection established for '{self.config.SPREADSHEET_NAME}'")
            return conn

    def _read_worksheet(self, worksheet_name: str) -> pd.DataFrame:
        """Read a single worksheet with rate limiting and error handling."""
        try:
            logger.info(f"Reading worksheet: {worksheet_name}")
            connection = self._get_connection()
            worksheet = connection.worksheet(worksheet_name)
            
            # Check row count for potential chunking
            row_count = worksheet.row_count
            if row_count > self.config.CHUNK_SIZE * 2:
                return self._read_worksheet_chunked(worksheet, row_count)
            
            records = worksheet.get_all_records()
            data = pd.DataFrame(records)
            
            if data.empty:
                logger.warning(f"Worksheet '{worksheet_name}' is empty")
                return pd.DataFrame()
            
            logger.info(f"Successfully read {len(data)} rows from {worksheet_name}")
            return data
            
        except gspread.exceptions.WorksheetNotFound as e:
            raise DataLoadError(f"Worksheet '{worksheet_name}' not found: {e}")
        except Exception as e:
            raise DataLoadError(f"Failed to read '{worksheet_name}': {e}")

    def _read_worksheet_chunked(self, worksheet, total_rows: int) -> pd.DataFrame:
        """Read a large worksheet in chunks to manage memory."""
        try:
            headers = worksheet.row_values(1)
            chunks = []
            
            for start_row in range(2, total_rows + 1, self.config.CHUNK_SIZE):
                end_row = min(start_row + self.config.CHUNK_SIZE - 1, total_rows)
                chunk = worksheet.get_values(f'A{start_row}:ZZ{end_row}')
                chunks.extend(chunk)
            
            return pd.DataFrame(chunks, columns=headers)
        except Exception as e:
            raise DataLoadError(f"Failed to read chunked worksheet: {e}")

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
        """Load all main data sheets in parallel for maximum performance."""
        cache_key = "all_data"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Using cached data package")
                return cached

        try:
            logger.info("Loading all data from Google Sheets with parallel execution...")
            
            results = {}
            
            # Parallel loading of all main sheets
            with ThreadPoolExecutor(max_workers=self.config.MAX_WORKERS) as executor:
                # Submit all tasks
                future_to_sheet = {
                    executor.submit(self._rate_limiter(self._read_worksheet), sheet_name): key
                    for key, sheet_name in self.config.MAIN_SHEETS.items()
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_sheet):
                    key = future_to_sheet[future]
                    try:
                        results[key] = future.result()
                        logger.info(f"✓ Loaded {key} successfully")
                    except Exception as e:
                        logger.error(f"✗ Failed to load {key}: {e}")
                        # Re-raise to abort the entire load
                        raise DataLoadError(f"Failed to load {key}: {e}")

            data_package = DataPackage(
                disease_stats=results['disease_stats'],
                database=results['database'],
                disease_codes=results['disease_codes'],
                geo_data=results['geo_data'],
                news_data=results['news_data'],
                weather_data=results['weather_data'],
                livestock_stats=results['livestock_stats'],
                loaded_at=datetime.now(),
            )

            self._cache.set(cache_key, data_package)
            logger.info("✓ All data loaded successfully with parallel execution")
            return data_package

        except Exception as e:
            raise DataLoadError(f"Failed to load data: {e}")

    def load_livestock_stats_data(
        self, use_cache: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame,
               pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load and preprocess livestock stats with parallel loading where possible."""
        cache_key = "livestock_stats"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Using cached livestock stats data")
                return cached

        try:
            # Load raw data in parallel where possible
            raw_data = {}
            
            # Sheets that can be loaded in parallel
            parallel_sheets = {
                'yearly_raw': self.config.YEARLY_NATIONAL_STATS_SHEET,
                'farm_raw': self.config.FARM_STATS_SHEET,
                'group_farming_raw': self.config.GROUP_FARMING_STATS,
                'breeding_raw': self.config.BREEDING_ANIMAL_STATS,
            }
            
            with ThreadPoolExecutor(max_workers=self.config.MAX_WORKERS) as executor:
                future_to_sheet = {
                    executor.submit(self._rate_limiter(self._read_worksheet_raw), sheet_name): key
                    for key, sheet_name in parallel_sheets.items()
                }
                
                for future in as_completed(future_to_sheet):
                    key = future_to_sheet[future]
                    try:
                        raw_data[key] = future.result()
                        logger.info(f"✓ Loaded raw {key}")
                    except Exception as e:
                        logger.error(f"✗ Failed to load {key}: {e}")
                        raise DataLoadError(f"Failed to load {key}: {e}")
            
            # Load remaining sheets
            livestock_stats = self._rate_limiter(self._read_worksheet)(
                self.config.LIVESTOCK_STATS_SHEET
            )
            stats_by_district = self._rate_limiter(self._read_worksheet)(
                self.config.STATS_BY_DISTRICT
            )
            
            # Process yearly national stats
            yearly_raw = raw_data['yearly_raw']
            if yearly_raw and len(yearly_raw) >= 3:
                yearly_df = create_multiindex_dataframe(yearly_raw)
                province = yearly_df.iloc[:, 0]
                years = [c for c in yearly_df.columns.get_level_values(0).unique() 
                        if str(c).isdigit()]

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
            farm_raw = raw_data['farm_raw']
            if farm_raw and len(farm_raw) >= 3:
                farm_df = create_multiindex_dataframe(farm_raw)
                province = farm_df.iloc[:, 0]
                
                data_farm = farm_df.xs('Farm', axis=1, level=1)
                data_amount = farm_df.xs('Amount', axis=1, level=1)
                
                data_farm.insert(0, 'Province', province)
                data_amount.insert(0, 'Province', province)
                
                data_farm = preprocess_livestock_df(data_farm)
                data_amount = preprocess_livestock_df(data_amount)
            else:
                data_farm, data_amount = pd.DataFrame(), pd.DataFrame()

            # Process group farming stats
            group_farming_raw = raw_data['group_farming_raw']
            if group_farming_raw and len(group_farming_raw) >= 3:
                farming_df = create_multiindex_dataframe(group_farming_raw)
                province = farming_df.iloc[:, 0]
                
                farming_amount_group = farming_df.xs('Amount of group', axis=1, level=1)
                farming_amount_animal = farming_df.xs('Amount of animal', axis=1, level=1)
                
                farming_amount_group.insert(0, 'Province', province)
                farming_amount_animal.insert(0, 'Province', province)
                
                farming_amount_group = preprocess_livestock_df(farming_amount_group)
                farming_amount_animal = preprocess_livestock_df(farming_amount_animal)
            else:
                farming_amount_group, farming_amount_animal = pd.DataFrame(), pd.DataFrame()

            # Process breeding stats
            breeding_raw = raw_data['breeding_raw']
            if breeding_raw:
                breeding_animal_stats = pd.DataFrame(breeding_raw)
                breeding_animal_stats = breeding_animal_stats.applymap(clean_cell_value)
            else:
                breeding_animal_stats = pd.DataFrame()

            # Process stats by district
            stats_by_district = preprocess_livestock_df(stats_by_district)

            result = (
                livestock_stats, df_24, df_25, data_farm, data_amount,
                stats_by_district, farming_amount_group, farming_amount_animal,
                breeding_animal_stats
            )
            self._cache.set(cache_key, result)
            logger.info("✓ All livestock stats processed successfully")
            return result

        except Exception as e:
            raise DataLoadError(f"Failed to load livestock stats: {e}")

    def refresh_cache(self) -> None:
        """Clear all cached data."""
        logger.info("Clearing data cache")
        self._cache.clear()
        logger.info(f"Cache stats: {self._cache.get_stats()}")

    def warm_up_cache(self) -> None:
        """Pre-load data to warm up the cache during off-peak times."""
        if not self._cache.is_fresh("all_data"):
            logger.info("Warming up data cache...")
            try:
                self.load_all_data(use_cache=False)
                logger.info("Cache warmed up successfully")
            except Exception as e:
                logger.error(f"Failed to warm up cache: {e}")

    def batch_update_worksheet(self, worksheet_name: str, 
                               data_with_headers: List[List]) -> bool:
        """Update a worksheet using batch operations for better performance."""
        try:
            connection = self._get_connection()
            worksheet = connection.worksheet(worksheet_name)
            
            num_rows = len(data_with_headers)
            num_cols = len(data_with_headers[0]) if data_with_headers else 0
            
            if num_rows == 0 or num_cols == 0:
                logger.warning(f"No data to update for {worksheet_name}")
                return False
            
            # Resize worksheet to match data dimensions
            worksheet.resize(rows=num_rows, cols=num_cols)
            
            # Use batch update for single operation
            col_letter = chr(64 + num_cols) if num_cols <= 26 else 'ZZ'
            range_name = f'A1:{col_letter}{num_rows}'
            
            worksheet.batch_update([{
                'range': range_name,
                'values': data_with_headers
            }])
            
            logger.info(f"Successfully batch updated {worksheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error in batch update for {worksheet_name}: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        return self._cache.get_stats()


# ─────────────────────────────────────────────────────────────────────────────
# Local Excel Loader (Development Mode) - Optimized
# ─────────────────────────────────────────────────────────────────────────────

class LocalExcelDataLoader:
    """Loads data from local Excel file in development mode."""

    def __init__(self, config: DataLoaderConfig):
        self.config = config
        self._cache = SimpleCache(ttl=config.CACHE_TTL)

    def load_all_data(self, use_cache: bool = True) -> DataPackage:
        cache_key = "all_data"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Using cached local Excel data")
                return cached

        try:
            logger.info(f"Loading data from local Excel: {self.config.LOCAL_EXCEL_PATH}")
            
            # Load all sheets in one go using pd.read_excel with sheet_name=None
            all_sheets = pd.read_excel(
                self.config.LOCAL_EXCEL_PATH,
                sheet_name=None,
                engine='openpyxl'
            )
            
            def get_sheet(name: str) -> pd.DataFrame:
                df = all_sheets.get(name)
                if df is None or df.empty:
                    logger.warning(f"Sheet '{name}' not found or empty in Excel")
                    return pd.DataFrame()
                return df

            data_package = DataPackage(
                disease_stats=get_sheet(self.config.DISEASE_STATS_SHEET),
                database=get_sheet(self.config.DATABASE_SHEET),
                disease_codes=get_sheet(self.config.DISEASE_CODE_SHEET),
                geo_data=get_sheet(self.config.GEO_DATA_SHEET),
                news_data=get_sheet(self.config.NEWS_DATA_SHEET),
                weather_data=get_sheet(self.config.WEATHER_DATA_SHEET),
                livestock_stats=get_sheet(self.config.LIVESTOCK_STATS_SHEET),
                loaded_at=datetime.now(),
            )

            self._cache.set(cache_key, data_package)
            logger.info("All data loaded successfully from local Excel")
            return data_package

        except Exception as e:
            raise DataLoadError(f"Failed to load local Excel data: {e}")

    def load_livestock_stats_data(
        self, use_cache: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame,
               pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load livestock stats from local Excel."""
        cache_key = "livestock_stats"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("Using cached local livestock stats")
                return cached

        try:
            # Read all sheets at once
            all_sheets = pd.read_excel(
                self.config.LOCAL_EXCEL_PATH,
                sheet_name=None,
                engine='openpyxl'
            )
            
            livestock_stats = all_sheets.get(self.config.LIVESTOCK_STATS_SHEET, pd.DataFrame())
            stats_by_district = all_sheets.get(self.config.STATS_BY_DISTRICT, pd.DataFrame())
            
            # For multi-level header sheets, we need to handle them differently
            # Since Excel might not preserve multi-level headers well, 
            # read them as raw data
            yearly_df = all_sheets.get(self.config.YEARLY_NATIONAL_STATS_SHEET, pd.DataFrame())
            farm_df = all_sheets.get(self.config.FARM_STATS_SHEET, pd.DataFrame())
            group_farming_df = all_sheets.get(self.config.GROUP_FARMING_STATS, pd.DataFrame())
            breeding_df = all_sheets.get(self.config.BREEDING_ANIMAL_STATS, pd.DataFrame())
            
            # Process DataFrames (simplified for local mode)
            df_24, df_25 = self._process_yearly_local(yearly_df)
            data_farm, data_amount = self._process_farm_local(farm_df)
            farming_amount_group, farming_amount_animal = self._process_group_local(group_farming_df)
            
            if not breeding_df.empty:
                breeding_animal_stats = breeding_df.applymap(clean_cell_value)
            else:
                breeding_animal_stats = pd.DataFrame()
            
            stats_by_district = preprocess_livestock_df(stats_by_district)
            
            result = (
                livestock_stats, df_24, df_25, data_farm, data_amount,
                stats_by_district, farming_amount_group, farming_amount_animal,
                breeding_animal_stats
            )
            self._cache.set(cache_key, result)
            return result

        except Exception as e:
            raise DataLoadError(f"Failed to load local livestock stats: {e}")

    def _process_yearly_local(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Process yearly stats from local Excel."""
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
        # Simplified processing for local mode
        return df, df  # Placeholder - implement based on actual Excel structure

    def _process_farm_local(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Process farm stats from local Excel."""
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
        return df, df  # Placeholder

    def _process_group_local(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Process group farming stats from local Excel."""
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
        return df, df  # Placeholder

    def refresh_cache(self) -> None:
        self._cache.clear()

    def warm_up_cache(self) -> None:
        if not self._cache.is_fresh("all_data"):
            self.load_all_data(use_cache=False)


# ─────────────────────────────────────────────────────────────────────────────
# Factory — returns the right loader based on ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────

def _make_loader(config: Optional[DataLoaderConfig] = None):
    """Create the appropriate data loader based on environment."""
    cfg = config or DataLoaderConfig()
    if IS_DEV:
        logger.info("Using LocalExcelDataLoader for development")
        return LocalExcelDataLoader(cfg)
    logger.info("Using GoogleSheetsDataLoader for production")
    return GoogleSheetsDataLoader(cfg)


# Singleton loader instance
_data_loader_instance = None
_loader_lock = threading.Lock()


def _get_data_loader(config: Optional[DataLoaderConfig] = None):
    """Get or create the singleton data loader instance."""
    global _data_loader_instance
    if _data_loader_instance is None:
        with _loader_lock:
            if _data_loader_instance is None:  # Double-checked locking
                _data_loader_instance = _make_loader(config)
    return _data_loader_instance


# ─────────────────────────────────────────────────────────────────────────────
# Data Processor (Unchanged - already optimized)
# ─────────────────────────────────────────────────────────────────────────────

class DataProcessor:
    """Processes and transforms loaded data for specific use cases."""

    @staticmethod
    def prepare_overview_data(data_package: DataPackage) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Prepare overview data with optimized column operations."""
        disease_stats = data_package.disease_stats.copy()
        
        # Vectorized column name cleaning
        disease_stats.columns = [
            col.replace("(Head)", "").replace("(Head", "").strip().upper()
            for col in disease_stats.columns
        ]
        
        # Vectorized numeric conversion for all columns except YEAR
        numeric_columns = [col for col in disease_stats.columns if col != "YEAR"]
        for col in numeric_columns:
            disease_stats[col] = pd.to_numeric(
                disease_stats[col].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(r"[^\d.]", "", regex=True)
                .str.strip()
                .replace("", "0"),
                errors='coerce'
            ).fillna(0).astype(int)
        
        if "YEAR" in disease_stats.columns:
            disease_stats["YEAR"] = pd.to_numeric(disease_stats["YEAR"], errors='coerce').fillna(0).astype(int)
            
        return disease_stats, data_package.weather_data.copy()

    @staticmethod
    def prepare_disease_analysis_data(data_package: DataPackage) -> pd.DataFrame:
        """Merge disease database with codes."""
        return pd.merge(
            data_package.database,
            data_package.disease_codes,
            on="disease_code",
            how="left",
        )

    @staticmethod
    def prepare_geographical_data(data_package: DataPackage) -> pd.DataFrame:
        """Return geographical data copy."""
        return data_package.geo_data.copy()

    @staticmethod
    def prepare_key_diseases_data(data_package: DataPackage) -> pd.DataFrame:
        """Merge disease data with geographical information."""
        database = data_package.database.copy()
        geo_data = data_package.geo_data.copy()
        
        # Find matching location column
        location_col = None
        for col in ["location", "region", "province", "district"]:
            if col in database.columns and col in geo_data.columns:
                location_col = col
                break
                
        if location_col is None:
            logger.warning("Could not find matching location column for merge")
            return database
            
        merged = pd.merge(
            database, geo_data, 
            on=location_col, 
            how="left", 
            suffixes=("", "_geo")
        )
        logger.info(f"Merged data on '{location_col}': {len(merged)} rows")
        return merged


# ─────────────────────────────────────────────────────────────────────────────
# Global cache — single load point for the whole app (Thread-safe)
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_DATA: Optional[DataPackage] = None
_GLOBAL_LIVESTOCK: Optional[Tuple] = None
_LAST_LOAD_TIME: Optional[float] = None
_global_lock = threading.Lock()

REFRESH_INTERVAL_SECONDS = 12 * 60 * 60  # 12 hours


def initialize_data(force: bool = False) -> DataPackage:
    """
    Load all sheet data (main data package + livestock stats) once and cache
    in module-level globals. Thread-safe.

    Call once at app startup (in app.py) before registering callbacks.
    Subsequent calls are no-ops unless `force=True` or
    REFRESH_INTERVAL_SECONDS has elapsed since the last load.
    """
    global _GLOBAL_DATA, _GLOBAL_LIVESTOCK, _LAST_LOAD_TIME

    with _global_lock:
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
            
            # Load main data package and livestock stats
            _GLOBAL_DATA = loader.load_all_data(use_cache=False)
            _GLOBAL_LIVESTOCK = loader.load_livestock_stats_data(use_cache=False)
            _LAST_LOAD_TIME = now
            
            # Log summary
            if _GLOBAL_DATA:
                summary = _GLOBAL_DATA.get_data_summary()
                logger.info(f"Data loaded: {summary}")

    return _GLOBAL_DATA


def load_data_package() -> DataPackage:
    """Return the cached global DataPackage, loading it if not yet initialized."""
    global _GLOBAL_DATA
    if _GLOBAL_DATA is None:
        return initialize_data()
    return _GLOBAL_DATA


def load_livestock_stats() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, 
                                     pd.DataFrame, pd.DataFrame, pd.DataFrame, 
                                     pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Return cached livestock statistics.
    
    Returns:
        Tuple of 9 DataFrames:
        (livestock_stats, df_2024, df_2025, data_farm, data_amount, 
         stats_by_district, farming_amount_group, farming_amount_animal, 
         breeding_animal_stats)
    """
    global _GLOBAL_LIVESTOCK
    if _GLOBAL_LIVESTOCK is None:
        initialize_data()
    return _GLOBAL_LIVESTOCK


# Convenience functions for specific data views
def load_overview_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Get processed overview data (disease stats + weather)."""
    return DataProcessor.prepare_overview_data(load_data_package())


def load_disease_analysis_data() -> pd.DataFrame:
    """Get merged disease analysis data."""
    return DataProcessor.prepare_disease_analysis_data(load_data_package())


def load_geographical_data() -> pd.DataFrame:
    """Get geographical data."""
    return DataProcessor.prepare_geographical_data(load_data_package())


def load_key_diseases_data() -> pd.DataFrame:
    """Get key diseases data merged with geo information."""
    return DataProcessor.prepare_key_diseases_data(load_data_package())


def refresh_all_data() -> DataPackage:
    """Force a full reload of all data. Call from a 'Refresh Data' button callback."""
    logger.info("Manual refresh triggered")
    return initialize_data(force=True)


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics for monitoring."""
    loader = _get_data_loader()
    return loader.get_cache_stats() if hasattr(loader, 'get_cache_stats') else {}


# ─────────────────────────────────────────────────────────────────────────────
# Write operations (admin panel) - Optimized with batch operations
# ─────────────────────────────────────────────────────────────────────────────

def update_disease_stats_worksheet(updated_data: pd.DataFrame) -> bool:
    """Update disease stats worksheet with batch operations (production only)."""
    if IS_DEV:
        logger.warning("[DEV] update_disease_stats_worksheet is a no-op in development mode")
        return True
    
    try:
        loader = _get_data_loader()
        
        # Prepare data with headers
        data_with_headers = [updated_data.columns.tolist()] + updated_data.values.tolist()
        
        # Use batch update for better performance
        success = loader.batch_update_worksheet(
            loader.config.DISEASE_STATS_SHEET,
            data_with_headers
        )
        
        if success:
            logger.info(f"Successfully updated {loader.config.DISEASE_STATS_SHEET}")
            # Invalidate relevant caches
            loader.refresh_cache()
            refresh_all_data()
            return True
        return False
        
    except Exception as e:
        logger.error(f"Error updating disease stats worksheet: {e}")
        return False


def add_new_case_to_database(new_case: dict) -> bool:
    """Add a new case to the disease database (production only)."""
    if IS_DEV:
        logger.warning("[DEV] add_new_case_to_database is a no-op in development mode")
        return True
    
    try:
        loader = _get_data_loader()
        connection = loader._get_connection()
        worksheet = connection.worksheet(loader.config.DATABASE_SHEET)
        
        # Get headers and create new row
        headers = worksheet.row_values(1)
        new_row_values = [new_case.get(col, "") for col in headers]
        
        # Append the new row
        worksheet.append_row(new_row_values)
        
        logger.info(f"Successfully added case to {loader.config.DATABASE_SHEET}")
        
        # Invalidate relevant caches
        loader.refresh_cache()
        refresh_all_data()
        return True
        
    except Exception as e:
        logger.error(f"Error adding case to database: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Health check and monitoring
# ─────────────────────────────────────────────────────────────────────────────

def health_check() -> Dict[str, Any]:
    """Perform a health check on the data loader."""
    try:
        loader = _get_data_loader()
        data = load_data_package()
        
        status = {
            "status": "healthy",
            "mode": "development" if IS_DEV else "production",
            "data_loaded": data is not None,
            "data_age_seconds": time.time() - _LAST_LOAD_TIME if _LAST_LOAD_TIME else None,
            "cache_stats": loader.get_cache_stats() if hasattr(loader, 'get_cache_stats') else {},
        }
        
        if data:
            status["data_summary"] = data.get_data_summary()
            
        return status
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "mode": "development" if IS_DEV else "production",
        }