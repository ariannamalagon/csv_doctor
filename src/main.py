from file_utils import remove_duplicates, clean_dataframe_with_mapping
import pandas as pd
import os
import json
from datetime import datetime
import chardet
import csv
import io
import re

DEBUG = False  # Set to True for verbose output when troubleshooting

# Define data storage directory
DATA_DIR = "/Users/ari/VScode Projects/csv_doctor/data_storage"

def resolve_paths(file_input):
    """Resolve input path, output directory, and base filename."""
    if os.path.isabs(file_input) or os.path.exists(file_input):
        input_path = file_input
        directory = os.path.dirname(file_input)
        base_name = os.path.basename(file_input).replace(".csv", "")
    else:
        input_path = os.path.join(DATA_DIR, file_input)
        directory = DATA_DIR
        base_name = file_input.replace(".csv", "")
    return input_path, directory, base_name

def repair_csv(input_path):
    """
    Repair malformed CSV by detecting and fixing unquoted fields with embedded delimiters.
    Returns tuple: (repaired_content, repairs_made_list)
    """
    repairs_made = []
    
    try:
        with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Warning: Could not read CSV for repair check: {e}")
        return None, []
    
    if len(lines) < 2:
        return None, []  # Not enough data to repair
    
    # Parse header to get expected column count
    try:
        header = lines[0].strip()
        # Count commas outside of quotes
        expected_cols = count_unquoted_delimiters(header, ',') + 1
    except Exception as e:
        if DEBUG:
            print(f"DEBUG: Could not parse header for repair: {e}")
        return None, []
    
    repaired_lines = [lines[0]]  # Keep header as-is
    
    # Patterns to detect fields that should be quoted
    CURRENCY_PATTERN = r'^\$[\d,]+\.?\d*$'  # $1,200.00
    NEGATIVE_AMOUNT_PATTERN = r'^\([\d,]+\.?\d*\)$'  # (45.67)
    EURO_PATTERN = r'^€[\d.,]+$'  # €1.250,50
    NUMERIC_WITH_COMMA_PATTERN = r'^[\d]+,[\d]{3}(\.\d{1,2})?$'  # 1,234.56
    
    for line_num, line in enumerate(lines[1:], start=2):
        # Count unquoted delimiters in this line
        actual_cols = count_unquoted_delimiters(line.strip(), ',') + 1
        
        # If column count matches, no repair needed
        if actual_cols == expected_cols:
            repaired_lines.append(line)
            continue
        
        # Line has too many columns - likely has unquoted comma in a field
        if actual_cols > expected_cols:
            if DEBUG:
                print(f"DEBUG: Row {line_num} has {actual_cols} cols (expected {expected_cols})")
            
            repaired_line = repair_line(
                line,
                expected_cols,
                [CURRENCY_PATTERN, NEGATIVE_AMOUNT_PATTERN, EURO_PATTERN, NUMERIC_WITH_COMMA_PATTERN]
            )
            
            if repaired_line != line:
                repaired_lines.append(repaired_line)
                repairs_made.append(f"Row {line_num}: Quoted currency/numeric fields")
                if DEBUG:
                    print(f"DEBUG: Repaired row {line_num}")
            else:
                repaired_lines.append(line)
        else:
            repaired_lines.append(line)
    
    # Convert back to string
    repaired_content = ''.join(repaired_lines)
    
    return repaired_content, repairs_made


def count_unquoted_delimiters(line, delimiter=','):
    """Count delimiters that are NOT inside quotes."""
    count = 0
    in_quotes = False
    quote_char = None
    
    for i, char in enumerate(line):
        if char in ['"', "'"]:
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None
        elif char == delimiter and not in_quotes:
            count += 1
    
    return count


def repair_line(line, expected_cols, patterns):
    """
    Attempt to repair a single line by quoting fields that match currency/numeric patterns.
    """
    line = line.rstrip('\n')
    
    # Split by comma but track which commas are already quoted
    fields = []
    current_field = ""
    in_quotes = False
    quote_char = None
    
    for char in line:
        if char in ['"', "'"]:
            if not in_quotes:
                in_quotes = True
                quote_char = char
                current_field += char
            elif char == quote_char:
                in_quotes = False
                quote_char = None
                current_field += char
            else:
                current_field += char
        elif char == ',' and not in_quotes:
            fields.append(current_field)
            current_field = ""
        else:
            current_field += char
    
    if current_field or line.endswith(','):
        fields.append(current_field)
    
    # Now we have too many fields - identify which ones should be merged
    # Strategy: merge consecutive unquoted fields that match currency patterns
    merged_fields = []
    i = 0
    
    while i < len(fields):
        field = fields[i].strip()
        
        # Check if this field matches any pattern
        if any(re.match(pattern, field) for pattern in patterns):
            # This looks like part of a currency amount
            # Collect consecutive numeric/currency-looking fields
            merged = field
            j = i + 1
            
            while j < len(fields) and j < i + 3:  # Merge up to 3 fields
                next_field = fields[j].strip()
                # Check if next field is just digits or looks like currency continuation
                if re.match(r'^\d+(\.\d{2})?$', next_field) or re.match(r'^\d+$', next_field):
                    merged += "," + next_field
                    j += 1
                else:
                    break
            
            # Quote the merged field
            merged_fields.append(f'"{merged}"')
            i = j
        else:
            merged_fields.append(field)
            i += 1
    
    # Rebuild line with expected number of columns
    if len(merged_fields) == expected_cols:
        return ','.join(merged_fields) + '\n'
    else:
        # Repair failed, return original
        return line + '\n'


def load_csv(input_path):
    """Load CSV with robust error handling, encoding detection, and delimiter detection."""
    # ADDED: Attempt CSV repair first
    repaired_content, repairs_made = repair_csv(input_path)
    
    if repairs_made:
        print(f"⚠️  CSV Repair: Fixed {len(repairs_made)} rows with misaligned delimiters")
        for repair in repairs_made:
            print(f"  - {repair}")
        print()
        
        # Use repaired content instead of file
        use_repaired = True
    else:
        use_repaired = False
    
    try:
        import chardet
    except ImportError:
        print("Warning: chardet not installed. Encoding detection will be limited.")
        print("Install with: pip install chardet")
        chardet = None
    
    import csv as csv_module
    
    ALLOWED_DELIMITERS = [',', ';', '\t', '|']
    
    skipped_rows = []  # ADDED: Track skipped rows
    
    # Debug - check file exists and has size
    if not use_repaired:
        try:
            file_size = os.path.getsize(input_path)
            if DEBUG:
                print(f"DEBUG: File size: {file_size} bytes")
        except Exception as e:
            print(f"ERROR: Could not get file size: {e}")
            return None, []  # CHANGED: return tuple
    
    # Try to detect encoding (from file or repaired content)
    detected_encoding = 'utf-8'
    if chardet:
        try:
            if use_repaired:
                raw_data = repaired_content.encode('utf-8')[:100000]
            else:
                with open(input_path, 'rb') as f:
                    raw_data = f.read(100000)
            
            result = chardet.detect(raw_data)
            detected_encoding = result['encoding'] or 'utf-8'
            confidence = result['confidence']
            print(f"Detected encoding: {detected_encoding} (confidence: {confidence:.0%})")
            
            if DEBUG:
                print(f"DEBUG: chardet result: {result}")
            
            if confidence < 0.5 and detected_encoding != 'ascii':
                print(f"⚠️  Low confidence encoding detection. Will try multiple encodings.")
        except Exception as e:
            print(f"Warning: Could not detect encoding, defaulting to utf-8: {e}")
    else:
        print("Using default encoding: utf-8")
    
    # Try to detect delimiter
    detected_delimiter = ','
    encodings_for_sniff = [detected_encoding, 'utf-8', 'latin1']
    
    for enc in encodings_for_sniff:
        try:
            if use_repaired:
                sample = repaired_content[:5000]
            else:
                with open(input_path, 'r', encoding=enc, errors='replace') as f:
                    sample_lines = []
                    for _ in range(20):
                        line = f.readline()
                        if line.strip():
                            sample_lines.append(line)
                        if len(sample_lines) >= 10:
                            break
                    sample = ''.join(sample_lines)
            
            if sample:
                sniffer = csv_module.Sniffer()
                detected = sniffer.sniff(sample, delimiters=''.join(ALLOWED_DELIMITERS)).delimiter
                
                if detected in ALLOWED_DELIMITERS:
                    detected_delimiter = detected
                    print(f"Detected delimiter: '{detected_delimiter}'")
                    break
        except Exception as e:
            continue
    
    # Try reading with detected encoding and delimiter
    encodings_to_try = [detected_encoding, 'utf-8', 'utf-8-sig', 'latin1', 'iso-8859-1']
    
    for encoding in encodings_to_try:
        # Try different quote characters
        quote_chars_to_try = ['"', "'", None]
        
        for quote_char in quote_chars_to_try:
            try:
                if DEBUG:
                    print(f"DEBUG: Attempting encoding='{encoding}', delimiter='{detected_delimiter}', quotechar={quote_char}")
                
                # ADDED: Capture skipped line info
                bad_lines_info = []
                
                def bad_line_handler(bad_line):
                    """Capture skipped lines for reporting."""
                    bad_lines_info.append(bad_line)
                    return None  # Skip the line
                
                # Read from repaired content or file
                if use_repaired:
                    df = pd.read_csv(
                        io.StringIO(repaired_content),
                        encoding=encoding,
                        delimiter=detected_delimiter,
                        skipinitialspace=True,
                        on_bad_lines=bad_line_handler,  # CHANGED
                        engine='python',
                        quotechar=quote_char if quote_char else None,
                        quoting=csv_module.QUOTE_NONE if quote_char is None else csv_module.QUOTE_MINIMAL
                    )
                else:
                    read_kwargs = {
                        'encoding': encoding,
                        'delimiter': detected_delimiter,
                        'skipinitialspace': True,
                        'on_bad_lines': bad_line_handler,  # CHANGED
                        'engine': 'python'
                    }
                    
                    if quote_char is not None:
                        read_kwargs['quotechar'] = quote_char
                    else:
                        read_kwargs['quoting'] = csv_module.QUOTE_NONE
                    
                    df = pd.read_csv(input_path, **read_kwargs)
                
                # ADDED: Process captured bad lines
                if bad_lines_info:
                    for bad_line in bad_lines_info:
                        skipped_rows.append({
                            "content": str(bad_line),
                            "issue": "Malformed row - field count mismatch"
                        })
                
                if DEBUG:
                    print(f"DEBUG: Successfully read CSV. Shape: {df.shape}")
                
                if df.shape[0] == 0:
                    print(f"Warning: CSV loaded but contains 0 data rows (only header)")
                    if DEBUG:
                        print(f"DEBUG: Columns detected: {list(df.columns)}")
                    continue
                
                # Structural sanity checks
                is_suspicious = False
                warnings = []
                
                # Check 1: Single column
                if df.shape[1] == 1:
                    is_suspicious = True
                    if use_repaired:
                        sample_text = repaired_content[:2000]
                    else:
                        with open(input_path, 'r', encoding=encoding, errors='replace') as f:
                            sample_lines = [f.readline() for _ in range(10)]
                            sample_text = ''.join([line for line in sample_lines if line.strip()])
                    
                    if any(delim in sample_text for delim in ALLOWED_DELIMITERS):
                        print(f"Warning: Only 1 column detected. Trying different delimiters...")
                        for delimiter in ALLOWED_DELIMITERS:
                            try:
                                if use_repaired:
                                    df_test = pd.read_csv(
                                        io.StringIO(repaired_content),
                                        encoding=encoding,
                                        delimiter=delimiter,
                                        skipinitialspace=True,
                                        on_bad_lines='warn',
                                        engine='python'
                                    )
                                else:
                                    df_test = pd.read_csv(
                                        input_path,
                                        encoding=encoding,
                                        delimiter=delimiter,
                                        skipinitialspace=True,
                                        on_bad_lines='warn',
                                        engine='python'
                                    )
                                if df_test.shape[1] > 1:
                                    print(f"Success with delimiter: '{delimiter}'")
                                    df = df_test
                                    is_suspicious = False
                                    break
                            except:
                                continue
                
                # Check 2: Unnamed columns
                unnamed_count = sum(1 for col in df.columns if 'Unnamed:' in str(col))
                if unnamed_count > df.shape[1] * 0.3:
                    warnings.append(f"⚠️  SUSPICIOUS: {unnamed_count}/{df.shape[1]} columns are 'Unnamed' - header may be missing or malformed")
                    is_suspicious = True
                
                # Check 3: Header contains delimiters
                first_col = str(df.columns[0])
                if any(delim in first_col for delim in [',', ';', '|', '\t']) and len(first_col) > 50:
                    warnings.append(f"⚠️  SUSPICIOUS: First column name looks like concatenated data - wrong delimiter or missing header")
                    is_suspicious = True
                
                # Check 4: Extremely sparse data
                if df.shape[1] > 1:
                    null_percentage = df.isnull().sum().sum() / (df.shape[0] * df.shape[1])
                    if null_percentage > 0.7:
                        warnings.append(f"⚠️  SUSPICIOUS: {null_percentage:.0%} of cells are empty - possible column misalignment")
                        is_suspicious = True
                
                # Check 5: Still single column after retries
                if df.shape[1] == 1 and is_suspicious:
                    warnings.append(f"⚠️  SUSPICIOUS: Only 1 column detected even after delimiter retries")
                
                print(f"Successfully loaded with encoding: {encoding}, quotechar={quote_char}")
                
                # SANITY CHECKS
                print(f"\n--- Load Sanity Check ---")
                print(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
                
                if df.shape[1] <= 20:
                    print(f"Columns: {list(df.columns)}")
                else:
                    print(f"Columns (first 20): {list(df.columns[:20])} ... and {df.shape[1] - 20} more")
                
                print(f"\nFirst 3 rows:")
                print(df.head(3))
                
                # Show warnings if any
                if warnings:
                    print(f"\n{'='*50}")
                    for warning in warnings:
                        print(warning)
                    print(f"{'='*50}\n")
                    
                    if is_suspicious and df.shape[1] == 1:
                        proceed = input("❌ Parse looks broken. Continue anyway? (y/n): ").strip().lower()
                        if proceed != 'y':
                            print("Load cancelled. Please check your file format.")
                            return None, []
                    else:
                        print("⚠️  Parse has warnings but will continue. Type 'x' to cancel or press Enter to proceed.")
                        proceed = input().strip().lower()
                        if proceed == 'x':
                            print("Load cancelled.")
                            return None, []
                
                return df, skipped_rows  # CHANGED: return tuple
                
            except UnicodeDecodeError as e:
                if DEBUG:
                    print(f"  ✗ Encoding {encoding} (quotechar={quote_char}) failed (UnicodeDecodeError)")
                continue
            except FileNotFoundError:
                print(f"Error: File not found at {input_path}")
                return None, []  # CHANGED: return tuple
            except pd.errors.EmptyDataError as e:
                if DEBUG:
                    print(f"  ✗ Encoding {encoding} (quotechar={quote_char}) failed (EmptyDataError)")
                continue
            except pd.errors.ParserError as e:
                if DEBUG:
                    print(f"  ✗ Encoding {encoding} (quotechar={quote_char}) failed (ParserError)")
                continue
            except Exception as e:
                if DEBUG:
                    print(f"  ✗ Encoding {encoding} (quotechar={quote_char}) failed ({type(e).__name__}): {str(e)[:50]}")
                continue
    
    print(f"Error: Could not load CSV with any attempted encoding/quoting combination")
    return None, []  # CHANGED: return tuple

def interactive_column_mapping(columns):
    """Prompt user to assign type to each column."""
    print("\nDetected columns:")
    for i, col in enumerate(columns, 1):
        print(f"{i}. {col}")
    
    column_map = {}
    valid_types = {"date", "money", "text", "number", "category"}
    
    # Ask about date format once upfront
    date_format_preference = None
    has_date_columns = False
    
    for col in columns:
        while True:
            col_type = input(f"\nAssign type for '{col}' (date/money/text/number/category): ").strip().lower()
            if col_type in valid_types:
                column_map[col] = col_type
                
                # If first date column, ask about format
                if col_type == "date" and not has_date_columns:
                    has_date_columns = True
                    print("\n--- Date Format Preference ---")
                    print("For ambiguous dates (e.g., 01/02/2024):")
                    print("  1. MM/DD/YYYY (US format)")
                    print("  2. DD/MM/YYYY (European format)")
                    print("  3. Auto-detect (pandas default - tries to infer)")
                    
                    while True:
                        pref = input("Choose (1/2/3): ").strip()
                        if pref == "1":
                            date_format_preference = "US"
                            break
                        elif pref == "2":
                            date_format_preference = "EU"
                            break
                        elif pref == "3":
                            date_format_preference = "AUTO"  # FIXED: explicit AUTO
                            break
                        else:
                            print("Invalid choice. Please enter 1, 2, or 3.")
                
                break
            else:
                print(f"Invalid type. Choose from: {', '.join(valid_types)}")
    
    return column_map, date_format_preference

def save_csv(raw_data, output_path):
    """Save cleaned CSV."""
    try:
        raw_data.to_csv(output_path, index=False)
        return True
    except PermissionError:
        print(f"Error: Permission denied writing to {output_path}")
    except Exception as e:
        print(f"Error saving file: {e}")
    return False

def save_summary(summary, output_path):
    """Save summary JSON next to the cleaned file (WITHOUT issues detail)."""
    summary_path = output_path.replace("_cleaned.csv", "_summary.json")
    
    # MODIFIED: Remove issues-related keys before saving to JSON
    summary_for_json = {k: v for k, v in summary.items() if k not in ['flagged_issues', 'skipped_rows_count']}
    
    try:
        with open(summary_path, "w") as f:
            json.dump(summary_for_json, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving summary: {e}")
    return False


def save_issues_report(flagged_issues, output_path, skipped_rows=None):
    """Save detailed issues report as JSON (both data quality issues and skipped rows)."""
    if not flagged_issues and not skipped_rows:
        return  # Silently skip if no issues
    
    issues_path = output_path.replace("_cleaned.csv", "_issues_report.json")
    
    # Combine flagged issues and skipped rows
    all_issues = {
        "data_quality_issues": flagged_issues,
        "skipped_rows": skipped_rows or []
    }
    
    try:
        with open(issues_path, "w") as f:
            json.dump(all_issues, f, indent=2)
        print(f"✓ Detailed issues report saved: {issues_path}")
    except Exception as e:
        print(f"Warning: Could not save issues report: {e}")


def format_summary_for_terminal(summary):
    """Pretty-print summary for terminal review with organized sections."""
    MAX_INVALID_DISPLAY = 5  # Cap terminal spam
    
    lines = [
        "\n" + "=" * 50,
        "DATA PROCESSING SUMMARY",
        "=" * 50,
        f"\nTimestamp: {summary['timestamp']}",
        f"\n--- Input/Output Stats ---",
        f"Total rows in: {summary['total_rows_in']}",
        f"Total rows out: {summary['total_rows_out']}",
        f"Missing values per column: {summary['missing_values_per_column']}",
        f"\n--- Column Changes ---",
        f"Columns renamed: {summary['columns_renamed']}",
        f"\n--- Rows Dropped ---",
    ]
    
    if summary['rows_dropped']:
        for drop in summary['rows_dropped']:
            lines.append(f"  • {drop}")
    else:
        lines.append("  • None")
    
    lines.append(f"\n--- Rows Added ---")
    if summary['rows_added']:
        for add in summary['rows_added']:
            lines.append(f"  • {add}")
    else:
        lines.append("  • None")
    
    lines.append(f"\n--- Formatting Applied ---")
    for change in summary['formatting_changes']:
        lines.append(f"  • {change}")
    
    if summary.get('invalid_dates_detected', 0) > 0 or summary.get('invalid_numeric_detected', 0) > 0:
        lines.append(f"\n--- Data Quality Issues ---")
        if summary.get('invalid_dates_detected', 0) > 0:
            lines.append(f"Invalid dates detected: {summary['invalid_dates_detected']}")
            if summary.get('invalid_date_values'):
                display_values = summary['invalid_date_values'][:MAX_INVALID_DISPLAY]
                lines.append(f"  Sample values: {', '.join(display_values)}")
                if len(summary['invalid_date_values']) > MAX_INVALID_DISPLAY:
                    lines.append(f"  ... and {len(summary['invalid_date_values']) - MAX_INVALID_DISPLAY} more")
        
        if summary.get('invalid_numeric_detected', 0) > 0:
            lines.append(f"Invalid numeric values detected: {summary['invalid_numeric_detected']}")
            if summary.get('invalid_amount_values'):
                display_values = list(map(str, summary['invalid_amount_values'][:MAX_INVALID_DISPLAY]))
                lines.append(f"  Sample values: {', '.join(display_values)}")
                if len(summary['invalid_amount_values']) > MAX_INVALID_DISPLAY:
                    lines.append(f"  ... and {len(summary['invalid_amount_values']) - MAX_INVALID_DISPLAY} more")
    
    # Show skipped rows in terminal
    if summary.get('skipped_rows_count', 0) > 0:
        lines.append(f"\n--- Skipped Rows (Malformed) ---")
        lines.append(f"Total skipped: {summary['skipped_rows_count']}")
    
    lines.append(f"\n--- Output ---")
    lines.append(f"Output file path: {summary['output_file_path']}")
    lines.append("=" * 50)
    
    return "\n".join(lines)


def process_file(file_input):
    """Process a single CSV file through all cleaning functions."""
    try:
        input_path, directory, base_name = resolve_paths(file_input)
        output_filename = f"{base_name}_cleaned.csv"
        output_path = os.path.join(directory, output_filename)

        result = load_csv(input_path)  # CHANGED: capture tuple
        if result is None or result[0] is None:
            return None
        
        raw_data, skipped_rows = result  # CHANGED: unpack

        while True:
            # Interactive column mapping with date format preference
            column_map, date_format_preference = interactive_column_mapping(list(raw_data.columns))
            
            # Summary metrics BEFORE cleaning
            total_rows_in = len(raw_data)

            raw_data_temp, duplicates_removed, columns_renamed, invalid_dates_count, invalid_amounts_count, formatting_changes, rows_dropped, invalid_date_values, invalid_amount_values, flagged_issues = clean_dataframe_with_mapping(raw_data.copy(), column_map, date_format_preference)
            
            if raw_data_temp is None:
                return None

            total_rows_out = len(raw_data_temp)
            missing_values = raw_data_temp.isna().sum().to_dict()

            # SANITY CHECK - show cleaned data types
            print(f"\n--- Cleaning Sanity Check ---")
            print(f"Data types after cleaning:")
            print(raw_data_temp.dtypes)
            print(f"\nInvalid counts:")
            print(f"  Dates: {invalid_dates_count}")
            print(f"  Numeric: {invalid_amounts_count}")
            print(f"  Duplicates removed: {duplicates_removed}")

            summary = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_rows_in": total_rows_in,
                "total_rows_out": total_rows_out,
                "missing_values_per_column": missing_values,
                "columns_renamed": columns_renamed,
                "rows_dropped": rows_dropped,
                "rows_added": [],
                "formatting_changes": formatting_changes,
                "output_file_path": output_path,
                "flagged_issues": flagged_issues,
                "skipped_rows_count": len(skipped_rows)  # ADDED
            }

            if invalid_dates_count > 0:
                summary["invalid_dates_detected"] = invalid_dates_count
                summary["invalid_date_values"] = invalid_date_values
            if invalid_amounts_count > 0:
                summary["invalid_numeric_detected"] = invalid_amounts_count
                summary["invalid_amount_values"] = invalid_amount_values

            print(format_summary_for_terminal(summary))

            confirm = input("\nSave cleaned file and summary? (y) to save, (r) to redo, or (x) to exit: ").strip().lower()
            if confirm == "r":
                print("Redoing column mapping...\n")
                continue
            elif confirm == "y":
                raw_data = raw_data_temp
                if not save_csv(raw_data, output_path):
                    return None
                save_summary(summary, output_path)
                save_issues_report(flagged_issues, output_path, skipped_rows)  # ADDED: pass skipped_rows
                return output_filename
            elif confirm == "x":
                print("Exiting program...")
                exit(0)
            else:
                print("Invalid input. Please enter 'y' to save, 'r' to redo, or 'x' to exit.")
    
    except Exception as e:
        print(f"Unexpected error processing file: {e}")
        return None

def main():
    print("Welcome to CSV Doctor!")
    print("(Enter filename or full path)")
    files_to_process = []
    
    while True:
        file_input = input("Enter CSV file to clean (or press Enter to start processing): ").strip()
        
        # If empty and we have files, start processing
        if not file_input and files_to_process:
            break
        
        # If empty and no files, prompt again
        if not file_input:
            print("Error: Please enter at least one filename.")
            continue
        
        # Validate file exists
        if os.path.isabs(file_input) or os.path.exists(file_input):
            file_path = file_input
        else:
            file_path = os.path.join(DATA_DIR, file_input)
        
        if not os.path.exists(file_path):
            print(f"Error: File not found. Please check the path and try again.")
            continue
        
        if not file_path.lower().endswith('.csv'):
            print("Error: Please provide a CSV file (.csv extension).")
            continue
        
        # File is valid, add to queue
        files_to_process.append(file_input)
        print(f"✓ Added: {os.path.basename(file_input)} ({len(files_to_process)} file(s) in queue)")
        
        # Ask if they want to add more
        add_more = input("\nAdd another file? (y/n): ").strip().lower()
        if add_more != 'y':
            break
    
    if not files_to_process:
        print("No files to process. Exiting.")
        return
    
    print(f"\n{'='*50}")
    print(f"Processing {len(files_to_process)} file(s)...")
    print(f"{'='*50}\n")
    
    successes = 0
    failures = 0

    for i, file_input in enumerate(files_to_process, 1):
        display_name = os.path.basename(file_input)
        print(f"\n[{i}/{len(files_to_process)}] Processing {display_name}...")
        print("-" * 50)
        
        output_filename = process_file(file_input)
        
        if output_filename:
            print(f"✓ Cleaned: {output_filename}")
            successes += 1
        else:
            print(f"✗ Failed to clean: {display_name}")
            failures += 1
    
    print(f"\n{'='*50}")
    print(f"BATCH COMPLETE")
    print(f"{'='*50}")
    print(f"Total files: {len(files_to_process)}")
    print(f"✓ Successes: {successes}")
    print(f"✗ Failures: {failures}")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()


