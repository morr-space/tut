import FinanceDataReader as fdr
from datetime import datetime

def fetch_kospi():
    # Get today's date
    today = datetime.today().strftime('%Y-%m-%d')
    
    # Fetch KOSPI data
    data = fdr.DataReader('KS11', start=today, end=today)
    
    if data.empty:
        print("No KOSPI data available for today.")
        return None
    
    return data.iloc[-1]  # Return the most recent data (today)

if __name__ == "__main__":
    kospi_data = fetch_kospi()
    if kospi_data is not None:
        print("Today's KOSPI Index Data:")
        print(kospi_data)