import asyncio
import sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on('console', lambda msg: sys.stdout.buffer.write(f'[BROWSER CONSOLE {msg.type}] {msg.text}\n'.encode('utf-8', errors='replace')))
        page.on('pageerror', lambda err: sys.stdout.buffer.write(f'[BROWSER PAGEERROR] {err}\n'.encode('utf-8', errors='replace')))
        page.on('requestfailed', lambda req: sys.stdout.buffer.write(f'[BROWSER REQ FAILED] {req.url} {req.failure}\n'.encode('utf-8', errors='replace')))
        print('Testing https://nexus-iot-5pmb.onrender.com ...')
        try:
            await page.goto('https://nexus-iot-5pmb.onrender.com', timeout=45000, wait_until='networkidle')
            await asyncio.sleep(3)
        except Exception as e:
            print('Goto exception:', e)
        title = await page.title()
        print('Page title:', title)
        has_shell = await page.query_selector('.shell') is not None
        has_spinner = await page.query_selector('.boot .spinner') is not None
        brand = await page.query_selector('.brand-name')
        brand_text = await brand.text_content() if brand else 'none'
        print(f'Has .shell: {has_shell}')
        print(f'Has .spinner: {has_spinner}')
        print(f'Brand text: {brand_text}')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
