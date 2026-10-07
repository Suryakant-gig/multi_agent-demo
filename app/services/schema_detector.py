from typing import List, Any
import pandas as pd
import numpy as np
from app.models.domain import ColumnMetadata


class SchemaDetector:
    """
    Infers data types, null statistics, cardinality, and classifies
    columns into numeric, temporal, or categorical.
    """

    @staticmethod
    def is_temporal_series(series: pd.Series) -> bool:
        if pd.api.types.is_datetime64_any_dtype(series):
            return True
        sample = series.dropna().head(10)
        if sample.empty:
            return False
        # Fast check if column has date/time in its name or parses ISO
        try:
            parsed = pd.to_datetime(sample, errors="coerce")
            return bool(parsed.notna().all())
        except Exception:
            return False

    @classmethod
    def detect_schema(cls, df: pd.DataFrame) -> List[ColumnMetadata]:
        columns_meta: List[ColumnMetadata] = []

        for col in df.columns:
            series = df[col]
            null_count = int(series.isna().sum())
            unique_count = int(series.nunique())
            
            is_numeric = bool(pd.api.types.is_numeric_dtype(series))
            is_temporal = cls.is_temporal_series(series)
            
            total_valid = len(series) - null_count
            is_categorical = (
                not is_temporal and (
                    isinstance(series.dtype, pd.CategoricalDtype) or
                    (not is_numeric and unique_count > 0 and (unique_count / max(total_valid, 1) < 0.2 or unique_count <= 20))
                )
            )

            # Determine human-friendly data type name
            if is_temporal:
                dtype_name = "datetime"
            elif pd.api.types.is_integer_dtype(series):
                dtype_name = "integer"
            elif pd.api.types.is_float_dtype(series):
                dtype_name = "float"
            elif pd.api.types.is_bool_dtype(series):
                dtype_name = "boolean"
            else:
                dtype_name = "string"

            # Sample non-null values
            sample_vals = series.dropna().head(3).tolist()
            # Convert numpy/pandas types to native python for JSON serialization
            sample_clean = []
            for v in sample_vals:
                if isinstance(v, (np.integer, np.int64)):
                    sample_clean.append(int(v))
                elif isinstance(v, (np.floating, np.float64)):
                    sample_clean.append(float(v))
                else:
                    sample_clean.append(str(v))

            columns_meta.append(
                ColumnMetadata(
                    name=col,
                    data_type=dtype_name,
                    null_count=null_count,
                    unique_count=unique_count,
                    is_numeric=is_numeric,
                    is_temporal=is_temporal,
                    is_categorical=is_categorical,
                    sample_values=sample_clean
                )
            )

        return columns_meta
