#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘寶動態商品頁面抓取器
從天貓日常組團活動頁面抓取商品信息，過濾 < 10元的商品
並上傳到 Google Sheet
"""

import json
import requests
from datetime import datetime
from typing import List, Dict, Optional
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import gspread
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials

class TaobaoScraper:
    """淘寶商品抓取器"""

    def __init__(self):
        self.url = "https://huodong.taobao.com/wow/a/act/tmall/dailygroup/21201/21856/wupr"
        self.products = []
        self.today = datetime.now().strftime("%Y-%m-%d")

    def setup_driver(self):
        """設置 Selenium WebDriver"""
        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # 可選：無頭模式
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        driver = webdriver.Chrome(options=chrome_options)
        return driver

    def scrape_products(self) -> List[Dict]:
        """抓取淘寶頁面商品信息"""
        driver = self.setup_driver()

        try:
            print("正在訪問淘寶頁面...")
            driver.get(self.url)

            # 等待頁面加載
            time.sleep(5)

            # 等待商品容器出現
            wait = WebDriverWait(driver, 10)

            print("等待商品列表加載...")
            # 嘗試找到商品容器
            try:
                wait.until(EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "[data-item-id], .item-card, [class*='product']")
                ))
            except:
                print("⚠️ 商品容器未找到，嘗試替代選擇器...")

            # 執行 JavaScript 抓取商品信息
            script = """
            (function() {
                const products = [];

                // 方法1: 查找商品卡片
                const items = document.querySelectorAll('[data-item-id]');

                if (items.length === 0) {
                    // 方法2: 查找其他商品容器
                    const containers = document.querySelectorAll('.item-card, [class*="good"], [class*="product"]');
                    for (let container of containers) {
                        const product = extractProductInfo(container);
                        if (product) products.push(product);
                    }
                } else {
                    for (let item of items) {
                        const product = extractProductInfo(item);
                        if (product) products.push(product);
                    }
                }

                function extractProductInfo(element) {
                    try {
                        return {
                            title: element.querySelector('[class*="title"], h2, .item-title')?.textContent?.trim(),
                            price: parseFloat(
                                element.querySelector('[class*="price"], .item-price, .price')?.textContent?.match(/\\d+\\.?\\d*/)?.[0]
                            ),
                            image: element.querySelector('img')?.src || element.querySelector('img')?.dataset?.src,
                            url: element.querySelector('a')?.href || element.href,
                            soldCount: element.querySelector('[class*="sold"], .sales-count')?.textContent,
                            shopName: element.querySelector('[class*="shop"], .seller')?.textContent?.trim(),
                            uploadDate: new Date().toLocaleDateString('zh-CN')
                        };
                    } catch (e) {
                        return null;
                    }
                }

                return products;
            })();
            """

            print("執行 JavaScript 抓取商品...")
            products_data = driver.execute_script(script)

            print(f"✓ 找到 {len(products_data)} 件商品")

            # 過濾單價 < 10元的商品
            filtered_products = [
                p for p in products_data
                if p and isinstance(p.get('price'), (int, float)) and p['price'] < 10
            ]

            print(f"✓ 過濾後 < 10元的商品: {len(filtered_products)} 件")

            return filtered_products

        except Exception as e:
            print(f"❌ 抓取出錯: {e}")
            return []

        finally:
            driver.quit()

    def save_to_google_sheet(self, products: List[Dict]):
        """將數據保存到 Google Sheet"""

        if not products:
            print("❌ 沒有商品數據可保存")
            return False

        try:
            print("正在連接 Google Sheet...")

            # 這裡需要你的 Google Service Account JSON 文件
            # 設置步驟見下方注釋
            gc = gspread.service_account(filename='credentials.json')

            # 創建或打開 Sheet
            sheet_name = f"taobao-{self.today}"

            # 嘗試打開現有 Sheet，否則創建新的
            try:
                sheet = gc.open(sheet_name)
            except gspread.exceptions.SpreadsheetNotFound:
                print(f"創建新 Sheet: {sheet_name}")
                sheet = gc.create(sheet_name)
                sheet.share('paulha.hkp@gmail.com', perm_type='user', role='owner')

            worksheet = sheet.sheet1

            # 設置表頭
            headers = ['上架日期', '品名', '單價', '已出售數量', '圖片', 'URL', '店鋪名稱']
            worksheet.insert_row(headers, 1)

            # 添加數據
            rows = []
            for product in products:
                row = [
                    product.get('uploadDate', self.today),
                    product.get('title', ''),
                    product.get('price', ''),
                    product.get('soldCount', ''),
                    product.get('image', ''),
                    product.get('url', ''),
                    product.get('shopName', '')
                ]
                rows.append(row)

            # 批量插入
            worksheet.insert_rows(rows, 2)

            print(f"✓ 成功保存 {len(products)} 件商品到 Google Sheet")
            print(f"📊 Sheet 名稱: {sheet_name}")
            print(f"🔗 URL: {sheet.url}")

            return True

        except Exception as e:
            print(f"❌ 保存到 Google Sheet 失敗: {e}")
            print("\n💡 Google Sheet 設置說明:")
            print("1. 訪問 https://console.cloud.google.com/")
            print("2. 創建服務帳戶並下載 JSON 密鑰")
            print("3. 將 JSON 文件保存為 credentials.json")
            print("4. 在 Google Sheet 中共享編輯權限給服務帳戶郵箱")
            return False

    def save_to_excel(self, products: List[Dict]):
        """將數據保存到 Excel 檔案（備選方案）"""
        try:
            import openpyxl
            from openpyxl.utils.dataframe import dataframe_to_rows
            import pandas as pd

            df = pd.DataFrame(products)
            df = df[['uploadDate', 'title', 'price', 'soldCount', 'image', 'url', 'shopName']]
            df.columns = ['上架日期', '品名', '單價', '已出售數量', '圖片', 'URL', '店鋪名稱']

            filename = f"taobao-{self.today}.xlsx"
            df.to_excel(filename, index=False)

            print(f"✓ 成功保存到 Excel: {filename}")
            return True

        except ImportError:
            print("❌ 需要安裝 openpyxl 和 pandas")
            print("執行: pip install openpyxl pandas")
            return False
        except Exception as e:
            print(f"❌ 保存 Excel 失敗: {e}")
            return False

    def run(self):
        """主程序"""
        print("=" * 50)
        print("🛍️  淘寶商品抓取器")
        print("=" * 50)
        print(f"目標 URL: {self.url}")
        print(f"日期: {self.today}")
        print(f"篩選條件: 單價 < 10元\n")

        # 抓取商品
        products = self.scrape_products()

        if not products:
            print("⚠️  沒有找到符合條件的商品")
            return

        # 嘗試保存到 Google Sheet
        if not self.save_to_google_sheet(products):
            # 如果 Google Sheet 失敗，保存到 Excel
            print("\n嘗試保存到 Excel 作為備選方案...")
            self.save_to_excel(products)

        print("\n✅ 完成！")


if __name__ == "__main__":
    scraper = TaobaoScraper()
    scraper.run()
