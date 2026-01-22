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
