import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time
import os

# API कॉल के लिए बेसिक कॉन्फिगरेशन
API_KEY = "mRy2GrFk53rDQPej5XKY+F+Mo1DFnzI="  # आपकी API key
BASE_URL = "https://mapi.indiamart.com/wservce/crm/crmListing/v2/"

# आपके द्वारा चुने गए हेडर्स
SELECTED_HEADERS = [
    "UNIQUE_QUERY_ID", "QUERY_TYPE", "QUERY_TIME", "SENDER_NAME", 
    "SENDER_MOBILE", "SENDER_EMAIL", "SUBJECT", "SENDER_COMPANY", 
    "SENDER_ADDRESS", "SENDER_CITY", "SENDER_STATE", "SENDER_PINCODE", 
    "SENDER_COUNTRY_ISO", "SENDER_MOBILE_ALT", "SENDER_PHONE", 
    "SENDER_PHONE_ALT", "SENDER_EMAIL_ALT", "QUERY_PRODUCT_NAME", 
    "QUERY_MESSAGE", "QUERY_MCAT_NAME", "CALL_DURATION", 
    "RECEIVER_MOBILE", "RECEIVER_CATALOG"
]

# Google Sheets API सेटअप
CREDENTIALS_PATH = "D:\Green Raise Coding\AUtoMation\website-e43c3-9143b9cf52fc.json"  # credentials.json फ़ाइल का पाथ यहां सेट करें
SHEET_NAME = "IndiaMartDataFromOct2024"  # अपनी Google Sheet का नाम यहां सेट करें

def setup_google_sheets():
    """Google Sheets API सेटअप करें और वर्कशीट वापस करें"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # जांचें कि credentials.json फ़ाइल मौजूद है या नहीं
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"त्रुटि: {CREDENTIALS_PATH} फ़ाइल नहीं मिली।")
        print("कृपया Google Cloud Console से अपना service account credentials डाउनलोड करें और इसे सही स्थान पर रखें।")
        return None
    
    try:
        credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_PATH, scope)
        gc = gspread.authorize(credentials)
        
        # शीट को नाम से खोलने की कोशिश करें
        try:
            # पहले मौजूदा शीट खोजने की कोशिश करें
            sheet = gc.open(SHEET_NAME)
            print(f"मौजूदा Google Sheet खोली गई: {sheet.title}")
        except gspread.exceptions.SpreadsheetNotFound:
            # अगर शीट नहीं मिली, तो नई बनाएं
            sheet = gc.create(SHEET_NAME)
            print(f"नई Google Sheet बनाई गई: {sheet.title}")
            print(f"Sheet ID: {sheet.id}")
            
            # आप इस शीट को शेयर कर सकते हैं (वैकल्पिक)
            # sheet.share('your-email@gmail.com', perm_type='user', role='writer')
        
        # पहली वर्कशीट का उपयोग करें या नई बनाएं
        try:
            worksheet = sheet.get_worksheet(0)
            if not worksheet:
                worksheet = sheet.add_worksheet(title="IndiaMART Data", rows="2000", cols="30")
        except:
            worksheet = sheet.add_worksheet(title="IndiaMART Data", rows="2000", cols="30")
        
        return worksheet
    
    except Exception as e:
        print(f"Google Sheets सेटअप में त्रुटि: {str(e)}")
        return None

def download_indiamart_data():
    """IndiaMART से डेटा डाउनलोड करें और Google Sheets में स्टोर करें"""
    worksheet = setup_google_sheets()
    if not worksheet:
        print("Google Sheets सेटअप नहीं कर सके। स्क्रिप्ट रोकी जा रही है।")
        return
    
    # पहले देखें कि हेडर्स पहले से हैं या नहीं
    try:
        existing_headers = worksheet.row_values(1)
        if not existing_headers:
            # हेडर्स जोड़ें
            worksheet.append_row(SELECTED_HEADERS)
            print("हेडर्स सफलतापूर्वक जोड़े गए।")
    except:
        worksheet.append_row(SELECTED_HEADERS)
        print("हेडर्स सफलतापूर्वक जोड़े गए।")
    
    # तारीखों का सेटअप
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # 1 साल पहले की तारीख
    
    current_start = start_date
    current_end = current_start + timedelta(days=7)
    
    # रिकॉर्ड काउंट के लिए काउंटर
    total_records = 0
    
    # ग्रेस पीरियड के साथ API कॉल्स करना
    while current_start < end_date:
        # यदि current_end अभी के समय से आगे है, तो उसे अभी के समय तक सीमित कर दें
        if current_end > end_date:
            current_end = end_date
        
        # तारीखों को स्ट्रिंग फॉर्मेट में कन्वर्ट करें
        start_str = current_start.strftime("%d-%b-%Y") 
        end_str = current_end.strftime("%d-%b-%Y")
        
        print(f"डाउनलोड हो रहा है: {start_str} से {end_str} तक का डेटा")
        
        # API रिक्वेस्ट भेजें
        params = {
            "glusr_crm_key": API_KEY,
            "start_time": start_str,
            "end_time": end_str
        }
        
        try:
            response = requests.get(BASE_URL, params=params)
            data = response.json()
            
            # डेटा चेक करें और प्रोसेस करें
            if data.get("STATUS") == "SUCCESS":
                records = data.get("RESPONSE", [])
                
                if records:
                    # डेटा को Google Sheet में अपेंड करें
                    rows_to_append = []
                    for record in records:
                        # केवल चुने गए हेडर्स के लिए डेटा निकालें
                        row_values = [record.get(header, "") for header in SELECTED_HEADERS]
                        rows_to_append.append(row_values)
                    
                    # बैच में सभी रो एक साथ जोड़ें (API कॉल्स कम करने के लिए)
                    if rows_to_append:
                        worksheet.append_rows(rows_to_append)
                    
                    total_records += len(records)
                    print(f"सफलतापूर्वक {len(records)} रिकॉर्ड्स प्राप्त किए और Google Sheet में अपेंड किए गए")
                else:
                    print("इस तिथि अंतराल के लिए कोई रिकॉर्ड नहीं मिला")
            else:
                print(f"एरर: {data.get('MESSAGE', 'अज्ञात त्रुटि')}")
        
        except Exception as e:
            print(f"API कॉल में एरर: {str(e)}")
        
        # अगले 7 दिनों के लिए तारीखें अपडेट करें
        current_start = current_end
        current_end = current_start + timedelta(days=7)
        
        # API रेट लिमिट से बचने के लिए 5 मिनट (300 सेकंड) का डिले
        if current_start < end_date:  # अंतिम लूप पर डिले न करें
            print(f"अगली API कॉल के लिए 5 मिनट प्रतीक्षा करें...")
            time.sleep(300)  # 5 मिनट का इंतरवल
    
    print(f"सभी डेटा डाउनलोड हो गया। कुल {total_records} रिकॉर्ड्स Google Sheet में सेव किए गए।")

if __name__ == "__main__":
    download_indiamart_data()