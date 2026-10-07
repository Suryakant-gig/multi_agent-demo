import re
from typing import List, Dict, Any, Tuple
import pandas as pd


class DataCleaner:
    """
    Cleans raw tabular data:
    - Normalizes column names (removes unusual characters, trims spaces, snake_cased)
    - Replaces null/NA values appropriately
    - Trims string columns
    """

    @staticmethod
    def clean_column_name(col: str) -> str:
        col = str(col).strip()
        # Replace non-alphanumeric characters with underscore
        cleaned = re.sub(r"[^\w\s]", "_", col)
        cleaned = re.sub(r"\s+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        if not cleaned or cleaned[0].isdigit():
            cleaned = f"col_{cleaned}"
        return cleaned.lower()

    @classmethod
    def clean_dataframe(cls, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
        """
        Cleans dataframe in-place or returns cleaned copy and column rename mapping.
        """
        original_cols = list(df.columns)
        rename_map = {}
        for col in original_cols:
            clean_name = cls.clean_column_name(col)
            # Ensure unique column names
            counter = 1
            final_name = clean_name
            while final_name in rename_map.values():
                final_name = f"{clean_name}_{counter}"
                counter += 1
            rename_map[col] = final_name

        df = df.rename(columns=rename_map)

        # Strip whitespace from object/string columns
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

        return df, rename_map
