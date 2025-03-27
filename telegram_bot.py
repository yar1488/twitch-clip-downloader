import requests
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from selenium.common.exceptions import TimeoutException, WebDriverException

TOKEN = "7569496269:AAGKxd5qH3eQG8_8I7A9vvDA6m59OBDUHms"
WP_API_URL = "https://prepodsteam.com/wp-json/twitch_clip/v1/download"

def download_clip(clip_url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service("/app/.chrome-for-testing/chromedriver-linux64/chromedriver")
    driver = None
    try:
        print(f"Запуск Selenium для клипа: {clip_url}")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        print("Загрузка главной страницы Twitch...")
        driver.get("https://www.twitch.tv")
        print("Добавление cookies...")
        driver.add_cookie({"name": "auth-token", "value": "db22vqowglkayt5wbfcyqy73hhplne"})
        driver.add_cookie({"name": "unique_id", "value": "0yURhlx1H41UmSWnm59mqgB9Ukkw0CmP"})
        print(f"Загрузка страницы клипа: {clip_url}")
        driver.get(clip_url)
        print("Поиск кнопки 'Поделиться'...")
        share_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Поделиться')]"))
        )
        share_button.click()
        print("Поиск ссылки на скачивание...")
        download_link = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'production.assets.clips.twitchcdn.net') and contains(., 'Скачать портретную версию')]"))
        )
        video_url = download_link.get_attribute("href")
        print(f"Скачивание видео по ссылке: {video_url}")
        response = requests.get(video_url, timeout=30)
        if response.status_code == 200:
            output_file = f"/tmp/clip_{os.urandom(4).hex()}_portrait.mp4"
            with open(output_file, "wb") as f:
                f.write(response.content)
            return True, output_file, video_url, os.path.getsize(output_file)
        else:
            return False, None, None, f"Ошибка скачивания: {response.status_code}"
    except TimeoutException as e:
        return False, None, None, f"Тайм-аут при загрузке страницы или элемента: {str(e)}"
    except WebDriverException as e:
        return False, None, None, f"Ошибка Selenium: {str(e)}"
    except Exception as e:
        return False, None, None, f"Неизвестная ошибка: {str(e)}"
    finally:
        if driver:
            driver.quit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь мне до 15 URL клипов с Twitch (по одному в строке или через пробел), и я скачаю портретные версии.")

async def download_portrait_clips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    clip_urls = re.findall(r'https?://[^\s]+', message_text)
    if not clip_urls:
        await update.message.reply_text("Не найдено ни одного URL клипа. Отправь ссылки на клипы Twitch.")
        return
    if len(clip_urls) > 15:
        await update.message.reply_text(f"Слишком много ссылок ({len(clip_urls)}). Максимум — 15. Отправь меньше ссылок.")
        return
    await update.message.reply_text(f"Начинаю обработку {len(clip_urls)} клипов...")
    try:
        response = requests.post(WP_API_URL, json={"clip_urls": clip_urls}, timeout=10)
        if response.status_code == 200:
            results = response.json()
            for i, result in enumerate(results, 1):
                if result.get('success'):
                    await update.message.reply_text(f"Обрабатываю клип {i}/{len(clip_urls)}...")
                    success, output_file, video_url, file_size_or_error = download_clip(result['clip_url'])
                    if success:
                        if file_size_or_error > 50 * 1024 * 1024:
                            await update.message.reply_text(f"Клип {i}/{len(clip_urls)} слишком большой ({file_size_or_error} байт). Вот ссылка: {video_url}")
                        else:
                            with open(output_file, "rb") as video:
                                await update.message.reply_video(video=video, caption=f"Клип {i}/{len(clip_urls)}")
                            os.remove(output_file)
                    else:
                        await update.message.reply_text(f"Ошибка с клипом {i}/{len(clip_urls)}: {file_size_or_error}")
                else:
                    await update.message.reply_text(f"Ошибка с клипом {i}/{len(clip_urls)}: {result.get('error')}")
            await update.message.reply_text("Скачивание завершено!")
        else:
            await update.message.reply_text(f"Ошибка сервера WordPress: {response.status_code} - {response.text}")
    except requests.exceptions.Timeout:
        await update.message.reply_text("Ошибка: WordPress API не отвечает (тайм-аут). Проверь сервер.")
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка при запросе к WordPress API: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"Неизвестная ошибка: {str(e)}")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_portrait_clips))
    application.run_polling()

if __name__ == "__main__":
    main()
