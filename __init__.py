import os
import logging
import json
import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline
import numpy as np
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from twilio.rest import Client
from azure.functions import HttpRequest, HttpResponse

def main(req: HttpRequest) -> HttpResponse:
    logging.info("Azure Function gestart.")

    # Laad de omgevingsvariabelen
    login_url = os.getenv("login_url")
    username = os.getenv("username")
    password = os.getenv("password")
    cloud_name = os.getenv("cloud_name")
    api_key = os.getenv("api_key")
    api_secret = os.getenv("api_secret")
    account_sid = os.getenv("account_sid")
    auth_token = os.getenv("auth_token")
    whatsapp_to = os.getenv("whatsapp_to")
    whatsapp_from = os.getenv("whatsapp_from")

    if not all([login_url, username, password, cloud_name, api_key, api_secret, account_sid, auth_token, whatsapp_to, whatsapp_from]):
        logging.error("Vereiste omgevingsvariabelen ontbreken.")
        return HttpResponse("Vereiste omgevingsvariabelen ontbreken.", status_code=500)

    try:
        # Selenium browser instellen
        driver = webdriver.Chrome()
        driver.get(login_url)

        # Selenium interacties
        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        username_field.send_keys(username)

        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".login-btn"))
        )
        next_button.click()

        password_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "outlined-adornment-password"))
        )
        password_field.send_keys(password)

        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".login-btn"))
        )
        login_button.click()

        # Data ophalen
        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "path.apexcharts-bar-area"))
        )

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        bars = soup.select("path.apexcharts-bar-area")

        prices = []
        for bar in bars:
            j_value = bar.get("j")
            price_value = bar.get("val")
            if j_value and price_value:
                prices.append({
                    "time": f"Tijdslot {j_value}",
                    "price": float(price_value)
                })

        driver.quit()

        # Controleer of er data is
        if not prices:
            return HttpResponse("Geen data gevonden.", status_code=200)

        # Grafiek maken
        times = [item['time'] for item in prices[:24]]
        price_values = [item['price'] for item in prices[:24]]

        x = np.arange(len(times))
        y = np.array(price_values)

        x_new = np.linspace(x.min(), x.max(), 300)
        spline = make_interp_spline(x, y, k=3)
        y_smooth = spline(x_new)

        plt.figure(figsize=(12, 6))
        plt.plot(x_new, y_smooth, linewidth=2.5)
        plt.title('Energieprijzen per uur')
        plt.xlabel('Tijd')
        plt.ylabel('Prijs (€)')
        plt.xticks(ticks=x, labels=times, rotation=45)
        plt.tight_layout()
        graph_filename = "/tmp/energy_prices.png"
        plt.savefig(graph_filename)
        plt.close()

        # Upload grafiek naar Cloudinary
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )

        upload_result = cloudinary.uploader.upload(
            graph_filename,
            public_id="energy_prices",
            overwrite=True,
            resource_type="image"
        )

        secure_url = upload_result["secure_url"]

        # WhatsApp-bericht verzenden via Twilio
        client = Client(account_sid, auth_token)
        tomorrow_date = datetime.now().strftime("%d-%m-%Y")

        message = client.messages.create(
            from_=f"whatsapp:{whatsapp_from}",
            to=f"whatsapp:{whatsapp_to}",
            body=f"Dit zijn de energieprijzen voor {tomorrow_date}!",
            media_url=[secure_url]
        )

        logging.info(f"Bericht verzonden: {message.sid}")
        return HttpResponse(f"Succesvol uitgevoerd. Bericht-ID: {message.sid}", status_code=200)

    except Exception as e:
        logging.error(f"Fout opgetreden: {str(e)}")
        return HttpResponse(f"Fout opgetreden: {str(e)}", status_code=500)
