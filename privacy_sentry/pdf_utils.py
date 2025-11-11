# -*- coding: utf-8 -*-
"""
Допоміжний модуль для генерації PDF з Markdown.
(v2.8) - Повернено до чистої Markdown-логіки (v2.7).
Використовує 'pdfkit' та 'markdown2'.
"""

import pdfkit
import markdown2
import logging
import os
import html

# Налаштування логера для цього модуля
logger = logging.getLogger("pdf_utils")
logger.setLevel(logging.INFO)

# --- (ОНОВЛЕНО v2.8) CSS СТИЛІ ДЛЯ PDF (Чистий Markdown) ---
# (Видалено непотрібні HTML-класи .category-header, .status-yes, .status-no)
PDF_CSS_STYLE = """
<style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
        font-size: 11pt;
        line-height: 1.5;
        color: #333;
        padding: 2cm;
    }
    h1, h2, h3, h4 {
        font-family: "Georgia", serif;
        color: #111;
        font-weight: 600;
        margin-top: 25px;
        margin-bottom: 10px;
    }
    h1 { font-size: 24pt; border-bottom: 2px solid #eee; padding-bottom: 5px; }
    h2 { font-size: 18pt; }
    h3 { font-size: 14pt; border-bottom: 1px solid #eee; padding-bottom: 3px; }
    code, pre {
        font-family: "Menlo", "Consolas", monospace;
        background-color: #f5f5f5;
        border-radius: 4px;
        padding: 2px 4px;
        font-size: 90%;
    }
    pre {
        padding: 10px 15px;
        overflow-x: auto;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 15px;
        border-spacing: 0;
    }
    th, td {
        border: 1px solid #ddd;
        padding: 10px;
        text-align: left;
        vertical-align: top;
    }
    th {
        background-color: #f9f9f9;
        font-weight: bold;
    }
    /* Стиль для першої колонки (Питання) в DPIA */
    table td:first-child {
        font-weight: bold;
        background-color: #fdfdfd;
        width: 30%; /* Фіксована ширина для першої колонки */
    }
    blockquote {
        border-left: 4px solid #eee;
        padding-left: 15px;
        color: #555;
        font-style: italic;
    }
</style>
"""

def create_pdf_from_markdown(content: str, is_html: bool, output_filename: str) -> str:
    """
    (ОНОВЛЕНО v2.8)
    Генерує PDF з Markdown. Параметр 'is_html' ігнорується,
    оскільки ми ЗАВЖДИ генеруємо з Markdown.
    
    :param content: Рядок, що містить Markdown.
    :param is_html: (Ігнорується)
    :param output_filename: Шлях до вихідного PDF.
    :return: Шлях до вихідного PDF.
    """
    logger.info(f"Починаю генерацію PDF (Режим Markdown v2.8): {output_filename}")

    try:
        # (v2.8) Ми ЗАВЖДИ використовуємо 'markdown2'
        logger.info("Режим Markdown (v2.8). Використовуємо 'markdown2'.")
        html_content = markdown2.markdown(
            content,
            extras=["tables", "fenced-code-blocks", "strike", "cuddled-lists", "break-on-newline"]
        )
        
        # 3. Додаємо CSS стилі
        html_full = f"<html><head><meta charset='UTF-8'>{PDF_CSS_STYLE}</head><body>{html_content}</body></html>"
        
        # 4. Налаштування для pdfkit
        options = {
            'page-size': 'A4',
            'margin-top': '1in',
            'margin-right': '0.75in',
            'margin-bottom': '1in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'quiet': ''
        }
        
        # 5. Генеруємо PDF
        pdfkit.from_string(html_full, output_filename, options=options)
        
        logger.info(f"PDF успішно створено: {output_filename}")
        return output_filename

    except IOError as e:
        if "No wkhtmltopdf executable found" in str(e):
            logger.error("!!! 'wkhtmltopdf' не знайдено. !!!")
            logger.error("Будь ласка, встановіть 'wkhtmltopdf' у вашій системі.")
            logger.error("Debian/Ubuntu: sudo apt install wkhtmltopdf")
            logger.error("Arch/Manjaro (AUR): yay -S wkhtmltopdf-static")
            logger.error("Fedora: sudo dnf install wkhtmltopdf")
            raise Exception("Помилка на сервері: 'wkhtmltopdf' не встановлено. PDF не може бути створений.")
        else:
            logger.error(f"Помилка вводу-виводу під час генерації PDF: {e}", exc_info=True)
            raise e
    except Exception as e:
        logger.error(f"Невідома помилка під час генерації PDF: {e}", exc_info=True)
        raise e

def clear_temp_file(filepath: str):
    """Видаляє тимчасовий PDF-файл після надсилання."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Тимчасовий файл видалено: {filepath}")
        else:
            logger.warning(f"TІMЧАСОВИЙ ФАЙЛ НЕ ЗНАЙДЕНО для видалення: {filepath}")
    except Exception as e:
        logger.error(f"Помилка під час видалення тимчасового файлу {filepath}: {e}")