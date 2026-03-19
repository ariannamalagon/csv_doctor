import pandas as pd


def standardize_column_names(raw_data):
    standardized_columns = [col.strip().lower().replace(" ", "_") for col in raw_data.columns]
    raw_data.columns = standardized_columns
    return raw_data


def standardize_data_values(raw_data):
    raw_data["category"] = raw_data["category"].str.strip().str.lower()
    raw_data["description"] = raw_data["description"].str.strip().str.lower()
    return raw_data


def clean_dates(raw_data):
    raw_data["date"] = pd.to_datetime(raw_data["date"], errors="coerce")
    return raw_data


def remove_duplicates(raw_data):
    raw_data = raw_data.drop_duplicates()
    return raw_data


def clean_amounts(raw_data):
    raw_data["amount"] = pd.to_numeric(raw_data["amount"], errors="coerce")
    return raw_data


def to_snake_case(col_name):
    """Convert column name to snake_case."""
    col_name = col_name.strip().lower()
    col_name = col_name.replace(" ", "_").replace("-", "_")
    # Remove any non-alphanumeric characters except underscores
    col_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in col_name)
    # Replace multiple underscores with single
    while '__' in col_name:
        col_name = col_name.replace('__', '_')
    return col_name.strip('_')


def normalize_amount_series(series):
    """Normalize currency strings to numeric-friendly format."""
    s = series.astype("string")
    s = s.str.strip()
    s = s.str.replace(r"[,$]", "", regex=True)
    s = s.str.replace(r"^\((.*)\)$", r"-\\1", regex=True)
    return s


def clean_dataframe_with_mapping(raw_data, column_map, date_format_preference=None):
    """Apply type-specific cleaning based on column mapping."""
    try:
        formatting_changes = []
        rows_dropped = []
        invalid_date_values = []
        invalid_amount_values = []
        flagged_issues = []  # ALWAYS initialize
        
        # Rename columns to snake_case
        rename_map = {col: to_snake_case(col) for col in raw_data.columns}
        raw_data = raw_data.rename(columns=rename_map)
        
        # Check for duplicate column names after renaming
        if len(set(raw_data.columns)) != len(raw_data.columns):
            duplicates = [col for col in raw_data.columns if list(raw_data.columns).count(col) > 1]
            raise ValueError(f"Column name collision after snake_case conversion: {set(duplicates)}")
        
        # Update column_map keys to match new names
        column_map = {rename_map[old]: val for old, val in column_map.items()}
        
        columns_renamed = {old: new for old, new in rename_map.items() if old != new}
        
        # Track invalid values
        invalid_dates_count = 0
        invalid_amounts_count = 0
        
        # Add flag columns for tracking invalid cells
        flag_cols_added = []
        
        # Apply all transformations FIRST
        for col, col_type in column_map.items():
            if col_type == "date":
                # Safer date normalization - only common separators
                raw_data[col] = raw_data[col].astype("string").str.strip()
                raw_data[col] = raw_data[col].str.replace(r"[/.]", "-", regex=True)
                
                # Apply date format preference
                if date_format_preference == "EU":
                    dayfirst = True
                elif date_format_preference == "US":
                    dayfirst = False
                else:  # AUTO or None - let pandas infer
                    dayfirst = None
                
                # Build to_datetime args conditionally
                parse_kwargs = {"errors": "coerce"}
                if dayfirst is not None:
                    parse_kwargs["dayfirst"] = dayfirst
                
                invalid_mask = raw_data[col].notna() & pd.to_datetime(raw_data[col], **parse_kwargs).isna()
                invalid_dates_count += int(invalid_mask.sum())
                
                if invalid_mask.any():
                    # Add flag column
                    flag_col = f"{col}_invalid"
                    raw_data[flag_col] = invalid_mask
                    flag_cols_added.append(flag_col)
                    
                    # Record each invalid cell (cap at 100 for memory)
                    invalid_rows = raw_data[invalid_mask].head(100)
                    for idx, row_val in zip(invalid_rows.index, invalid_rows[col]):
                        invalid_date_values.append(row_val)
                        flagged_issues.append({
                            "row": int(idx) + 2,  # +2 for header and 0-indexing
                            "column": col,
                            "value": row_val,
                            "issue": "Invalid date format"
                        })
                
                raw_data[col] = pd.to_datetime(raw_data[col], **parse_kwargs)
                date_msg = f"{col}: Normalized date separators and converted to datetime"
                if date_format_preference and date_format_preference != "AUTO":
                    date_msg += f" ({date_format_preference} format)"
                elif date_format_preference == "AUTO":
                    date_msg += " (auto-detected format)"
                formatting_changes.append(date_msg)
            
            elif col_type == "money":
                normalized = normalize_amount_series(raw_data[col])
                invalid_mask = normalized.notna() & pd.to_numeric(normalized, errors="coerce").isna()
                invalid_amounts_count += int(invalid_mask.sum())
                
                if invalid_mask.any():
                    # Add flag column
                    flag_col = f"{col}_invalid"
                    raw_data[flag_col] = invalid_mask
                    flag_cols_added.append(flag_col)
                    
                    # Record each invalid cell (cap at 100)
                    invalid_rows = raw_data[invalid_mask].head(100)
                    for idx, row_val in zip(invalid_rows.index, invalid_rows[col]):
                        invalid_amount_values.append(row_val)
                        flagged_issues.append({
                            "row": int(idx) + 2,
                            "column": col,
                            "value": row_val,
                            "issue": "Invalid numeric format"
                        })
                
                raw_data[col] = pd.to_numeric(normalized, errors="coerce")
                formatting_changes.append(f"{col}: Stripped currency symbols, converted to numeric (kept as float)")
            
            elif col_type == "number":
                invalid_mask = raw_data[col].notna() & pd.to_numeric(raw_data[col], errors="coerce").isna()
                
                if invalid_mask.any():
                    flag_col = f"{col}_invalid"
                    raw_data[flag_col] = invalid_mask
                    flag_cols_added.append(flag_col)
                    
                    invalid_rows = raw_data[invalid_mask].head(100)
                    for idx, row_val in zip(invalid_rows.index, invalid_rows[col]):
                        flagged_issues.append({
                            "row": int(idx) + 2,
                            "column": col,
                            "value": row_val,
                            "issue": "Invalid numeric format"
                        })
                
                raw_data[col] = pd.to_numeric(raw_data[col], errors="coerce")
                formatting_changes.append(f"{col}: Converted to numeric format")
            
            elif col_type == "category":
                # Category: lowercase + trim
                raw_data[col] = raw_data[col].astype("string").str.strip().str.lower()
                formatting_changes.append(f"{col}: Standardized to lowercase, whitespace trimmed")
            
            elif col_type == "text":
                # Text: ONLY trim whitespace (preserve case for IDs, names, SKUs)
                raw_data[col] = raw_data[col].astype("string").str.strip()
                formatting_changes.append(f"{col}: Whitespace trimmed (case preserved)")
        
        # Remove duplicates AFTER normalization
        before_dedup = len(raw_data)
        raw_data = remove_duplicates(raw_data)
        duplicates_removed = before_dedup - len(raw_data)
        if duplicates_removed > 0:
            rows_dropped.append(f"Duplicate rows: {duplicates_removed}")
        
        if flag_cols_added:
            formatting_changes.append(f"Added flag columns: {', '.join(flag_cols_added)}")
        
        # ALWAYS return flagged_issues (even if empty)
        return raw_data, duplicates_removed, columns_renamed, invalid_dates_count, invalid_amounts_count, formatting_changes, rows_dropped, invalid_date_values, invalid_amount_values, flagged_issues
    
    except Exception as e:
        print(f"Error during data cleaning: {e}")
        # Return empty list for flagged_issues even on error
        return None, None, None, None, None, None, None, None, None, []
