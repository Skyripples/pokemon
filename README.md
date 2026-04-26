# Pokemon 專案入口

## V1.0 功能

- 根目錄提供靜態網站入口。
- `mezastar/` 提供 Pokemon Mezastar 店址地圖頁。
- 使用官方 Mezastar 店址 API 爬取店家資料。
- 將 `1072` 筆店家資料儲存在 `mezastar/data/mezastar_locations.json`。
- 每筆店家資料都已補上 `lat` / `lng`，地圖載入時不需要逐筆定位。
- 地圖支援店名與地址搜尋、定位到指定店家、開啟 Google Maps。
- Python 腳本集中放在 `mezastar/module/`。
- Mezastar 專用設定放在 `mezastar/setting/`。

## 目前架構

- `index.html`：根目錄靜態入口頁。
- `style.css`：根目錄入口頁樣式。
- `main.js`：根目錄入口頁腳本。
- `main.py`：根目錄執行入口，可指定同步設定、爬取資料或補座標。
- `mezastar/`：Mezastar 靜態網站。
- `mezastar/data/`：Mezastar 店家資料。
- `mezastar/module/`：Mezastar Python 腳本。
- `mezastar/setting/.env`：本機 Google Maps API Key 設定，不會提交到 git。
- `mezastar/setting/.env.example`：`.env` 範例。
- `data/`：寶可夢資料工作區。
- `setting/`：共用需求檔工作區。

## Mezastar 設定

建立 `mezastar/setting/.env`：

```env
GOOGLE_MAPS_API_KEY=YOUR_GOOGLE_MAPS_API_KEY
```

依照 `.env` 產生前端使用的 `mezastar/config.js`：

```powershell
.\.venv\Scripts\python.exe .\mezastar\module\sync_map_config.py
```

`mezastar/config.js` 只會留在本機，已加入 `.gitignore`，不要提交到 GitHub。
如果要查看前端設定格式，可參考 `mezastar/config.example.js`。

## Mezastar 指令

重新爬取官方店址資料：

```powershell
.\.venv\Scripts\python.exe .\mezastar\module\scrape_stores.py
```

補上缺少的經緯度：

```powershell
.\.venv\Scripts\python.exe .\mezastar\module\geocode_stores.py
```

只測試少量座標補齊：

```powershell
.\.venv\Scripts\python.exe .\mezastar\module\geocode_stores.py --limit 5
```

從根目錄執行指定流程：

```powershell
.\.venv\Scripts\python.exe .\main.py --sync-config
.\.venv\Scripts\python.exe .\main.py --scrape
.\.venv\Scripts\python.exe .\main.py --geocode
```

## 靜態網站

- 根目錄入口：`index.html`
- Mezastar 地圖頁：`mezastar/index.html`

GitHub Pages 可直接使用 `main` branch 的 root 作為靜態網站來源。

## 注意事項

- `mezastar/setting/.env` 是本機設定檔，不會提交到 git。
- `mezastar/config.js` 是由 `.env` 產生的本機設定檔，不會提交到 git。
- 目前只保留 `V1.0` 作為第一版發布。
