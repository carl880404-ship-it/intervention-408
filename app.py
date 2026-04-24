import streamlit as st
import yfinance as yf
from google import genai
import os
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import feedparser
import urllib.parse

@st.cache_data(ttl=3600)
def get_economic_context(query="日本 経済指標 予定 ニュース"):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    feed = feedparser.parse(rss_url)
    context = ""
    for entry in feed.entries[:10]:
        context += f"- {entry.title} ({entry.published})\n"
    return context if context else "ニュースの取得に失敗しました。"

st.set_page_config(page_title="Intervention 408", page_icon="📈", layout="wide")

# 保存先ファイルの定義
PORTFOLIO_FILE = "portfolio_data.csv"
FAVORITES_FILE = "favorites_data.csv"

def save_data(df, filename):
    try:
        df.to_csv(filename, index=False)
    except Exception as e:
        st.error(f"データの保存に失敗しました ({filename}): {e}")

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            return pd.read_csv(PORTFOLIO_FILE)
        except Exception:
            pass
    # デフォルトデータ
    return pd.DataFrame([
        {"Ticker": "7203.T", "Shares": 100, "Avg Cost": 2500},
        {"Ticker": "AAPL", "Shares": 10, "Avg Cost": 150}
    ])

def save_favorites():
    try:
        fav_df = pd.DataFrame(st.session_state.favorites, columns=["Code", "Name"])
        fav_df.to_csv(FAVORITES_FILE, index=False)
    except Exception:
        pass

def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        try:
            fav_df = pd.read_csv(FAVORITES_FILE)
            return [tuple(x) for x in fav_df.values]
        except Exception:
            pass
    return []

# Session State初期化
if 'search_history' not in st.session_state:
    st.session_state.search_history = []
if 'favorites' not in st.session_state:
    st.session_state.favorites = load_favorites()
if 'ticker_widget' not in st.session_state:
    st.session_state.ticker_widget = "7203"
if 'my_portfolio' not in st.session_state:
    st.session_state.my_portfolio = load_portfolio()
if 'portfolio_analysis' not in st.session_state:
    st.session_state.portfolio_analysis = None
if 'portfolio_results' not in st.session_state:
    st.session_state.portfolio_results = None

import time

def set_ticker(symbol_code):
    st.session_state.ticker_widget = symbol_code

def safe_generate_content(client, model, prompt, max_retries=2):
    """Gemini APIの429エラー(制限超過)をハンドリングし、再試行するラッパー関数"""
    for i in range(max_retries + 1):
        try:
            return client.models.generate_content(model=model, contents=prompt)
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                if i < max_retries:
                    wait_time = 15  # 無料枠の制限解除を待つための標準的な待機時間
                    st.warning(f"⚠️ API制限に達しました。{wait_time}秒後に自動的に再試行します... ({i+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    st.error("❌ APIの制限回数を超過しました。しばらく時間をおくか、サイドバーから別のモデル（2.0-flashなど）に切り替えてお試しください。")
                    raise e
            else:
                raise e

st.title("Intervention 408")

st.markdown("""
Streamlitとyfinanceを使って株価データを表示し、専用AI「Cheyanne」が最近のトレンドと業績予想を分析するアプリです。
""")

# Gemini APIキーの読み込み
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    api_key = st.sidebar.text_input("🗝️ Gemini API Key", type="password", help="環境変数 GEMINI_API_KEY が未設定の場合はこちらに入力してください。")

st.sidebar.markdown("---")
# 1.5系はサポート外の可能性があるため、2.5/2.0系に限定
model_choice = st.sidebar.selectbox(
    "🤖 Geminiモデルの選択",
    ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-pro"],
    help="「503 UNAVAILABLE」エラーなどが出た場合、別のモデルに切り替えると成功することがあります。"
)
st.sidebar.info("💡 **無料枠のコツ**: \n制限エラー(429)が出た場合は、上のモデルを別のもの（例：2.5 → 2.0）に切り替えるか、1分ほど待ってからお試しください。")

# サイドバー: オプション
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ オプション")
st.sidebar.checkbox("📈 ETFモード (ETFに特化した分析・推奨)", key="etf_mode")
market_choice = st.sidebar.radio("🌍 対象市場", ["日本", "米国/海外"], help="日本株か米国/海外株(ETF含む)かを選択します")

# サイドバー: お気に入りと履歴
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ お気に入り")
if st.session_state.favorites:
    for fav_code, fav_name in st.session_state.favorites:
        st.sidebar.button(f"{fav_code} {fav_name}", key=f"btn_fav_{fav_code}", on_click=set_ticker, args=(fav_code,))
else:
    st.sidebar.info("未登録")

st.sidebar.subheader("🕒 検索履歴")
if st.session_state.search_history:
    for hist_code, hist_name in reversed(st.session_state.search_history[-5:]):
        st.sidebar.button(f"{hist_code} {hist_name}", key=f"btn_hist_{hist_code}", on_click=set_ticker, args=(hist_code,))
else:
    st.sidebar.info("なし")

if not api_key:
    st.warning("⚠️ Gemini APIキーが設定されていません。Cheyanneの分析機能を利用するには、画面左側のサイドバーを開いてAPIキーを入力してください。")
else:
    client = genai.Client(api_key=api_key)

st.markdown("---")

tab_macro, tab_analysis, tab_portfolio = st.tabs(["🌍 グローバル＆発見", "📊 個別銘柄分析", "💼 ポートフォリオ診断"])

with tab_macro:
    # --- セクター強度ランキング (Sector Pulse) ---
    st.subheader("🔥 セクター強度ランキング (過去1週間)")
    st.markdown("主要セクターの代表ETFから、直近1週間の資金流入トレンドを分析します。")

    with st.spinner("セクターデータを集計中..."):
        # セクター代表ティッカー (日米)
        sector_map = {
            "🇯🇵 日経平均": "1321.T", "🇯🇵 自動車": "1622.T", "🇯🇵 電機/テク": "1625.T",
            "🇯🇵 銀行/金融": "1629.T", "🇯🇵 情報通信": "1630.T", "🇯🇵 不動産": "1631.T",
            "🇺🇸 テック": "XLK", "🇺🇸 金融": "XLF", "🇺🇸 ヘルスケア": "XLV",
            "🇺🇸 エネルギー": "XLE", "🇺🇸 資本財": "XLI", "🇺🇸 一般消費": "XLY"
        }
        
        try:
            # 過去1週間のデータを一括取得
            s_tickers = list(sector_map.values())
            s_data = yf.download(s_tickers, period="1wk", interval="1d", group_by='ticker', progress=False)
            
            # 日本と米国を分けて集計
            jp_results = []
            us_results = []
            import pandas as pd
            for name, sym in sector_map.items():
                if sym in s_data:
                    # NaNを除去して有効な終値のみを抽出
                    close = s_data[sym]['Close'].dropna()
                    if len(close) >= 2:
                        ret = (close.iloc[-1] / (close.iloc[0] if close.iloc[0] != 0 else 1) - 1) * 100
                        if not pd.isna(ret):
                            res = {"name": name, "return": ret}
                            if "🇯🇵" in name: jp_results.append(res)
                            else: us_results.append(res)
            
            # それぞれ上位3つを抽出
            jp_top = sorted(jp_results, key=lambda x: x['return'], reverse=True)[:3]
            us_top = sorted(us_results, key=lambda x: x['return'], reverse=True)[:3]
            
            # 左右に分けて表示
            l_col, r_col = st.columns(2)
            with l_col:
                st.markdown("##### 🇯🇵 日本株・上位セクター")
                for s in jp_top:
                    st.metric(s['name'], f"{s['return']:+.2f}%")
            with r_col:
                st.markdown("##### 🇺🇸 米国株・上位セクター")
                for s in us_top:
                    st.metric(s['name'], f"{s['return']:+.2f}%")
                    
        except Exception as e:
            st.error(f"セクターデータの取得に失敗しました: {e}")
    
    st.markdown("---")

    # --- AI経済カレンダー & 影響予測 & Idea Lab ---
    ec_col1, ec_col2 = st.columns([1, 1])
    
    with ec_col1:
        st.subheader("📅 AI経済カレンダー & 影響予測")
        st.markdown("直近1週間の重要イベントが、保有銘柄に与えるインパクトをAIが予測します。")
        if st.button("🔔 予測報告を生成", use_container_width=True):
            with st.spinner("カレンダーを解析し、インパクトをシミュレーション中..."):
                news_context = get_economic_context()
                # 保有銘柄の情報を取得（あれば）
                portfolio_tickers = st.session_state.my_portfolio['Ticker'].tolist() if not st.session_state.my_portfolio.empty else []
                
                cal_prompt = f"""
あなたはプロの投資ストラテジスト「Cheyanne」です。
最新のニュースと以下の保有銘柄情報に基づき、来週にかけての重要イベント（経済指標、決算等）と、
それがユーザーの資産に与える具体的なプラス・マイナスのインパクトを予測してください。

【保有銘柄】: {", ".join(portfolio_tickers) if portfolio_tickers else "なし（一般的な市場予測を行ってください）"}

【最新ニュース/材料】:
{news_context}

【報告形式】:
- 「来週の重要イベント3選」とその影響度
- 各保有銘柄（または関連セクター）への個別インパクト予測
- 事前のアクションアドバイス
"""
                try:
                    res_cal = safe_generate_content(client, model_choice, cal_prompt)
                    st.info("📅 Cheyanneの予測レポート")
                    st.markdown(res_cal.text)
                except Exception as e:
                    st.error(f"予測中にエラーが発生しました: {e}")

    with ec_col2:
        st.subheader("💡 Idea Lab (本日のお宝銘柄)")
        st.markdown("現在の市況とニュースから、AIが「今こそ注目すべき」日米の2銘柄を厳選します。")
        if st.button("💎 お宝銘柄を選定", use_container_width=True):
            with st.spinner("セクタートレンドと材料を分析中..."):
                idea_prompt = f"""
あなたは凄腕のファンドマネージャー「Cheyanne」です。
現在の世界的なセクタートレンドと最新ニュースから、
「今、個人投資家が仕込むべき日米のお宝銘柄」をそれぞれ1つずつ選定してください。
ティッカー、理由、リスクを明示してください。
"""
                try:
                    res_idea = safe_generate_content(client, model_choice, idea_prompt)
                    st.success("💎 Cheyanne's Selection")
                    st.markdown(res_idea.text)
                except Exception as e:
                    st.error(f"銘柄選定中にエラーが発生しました: {e}")

    st.markdown("---")
    # 世界各国の経済情報・ニュース
    with st.expander("🌍 世界各国の経済情報・ニュース", expanded=False):
        st.markdown("対象国を選択すると、その国の最新経済ニュースとCheyanneによる経済状況の分析を表示します。")
    
        country_list = [
            "日本", "アメリカ", "韓国", "中国", "香港", "台湾", "イギリス", "ドイツ", "フランス", "イタリア", 
            "スペイン", "スイス", "オーストリア", "スウェーデン", "フィンランド", "ベルギー", "南アフリカ", 
            "エジプト", "ナイジェリア", "サウジアラビア", "マレーシア", "タイ", "インドネシア", "インド", 
            "シンガポール", "オーストラリア", "ブラジル", "メキシコ", "トルコ",
            "オランダ", "UAE", "デンマーク", "カナダ", "ポーランド", "フィリピン"
        ]
        selected_country = st.selectbox("対象国を選択してください", country_list)
    
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            btn_country_news = st.button(f"📰 最新経済ニュースを取得", use_container_width=True)
        with col_c2:
            btn_country_ai = st.button(f"🤖 経済をCheyanneで分析", use_container_width=True)
        with col_c3:
            btn_country_adr = st.button(f"🏢 米国上場のおすすめ企業", use_container_width=True)
        
        if btn_country_news:
            with st.spinner(f"{selected_country}の経済ニュースを取得中..."):
                import urllib.request
                import urllib.parse
                import xml.etree.ElementTree as ET
                from email.utils import parsedate_to_datetime
                import datetime
            
                query = f"{selected_country} 経済"
                encoded_query = urllib.parse.quote(query)
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
            
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        xml_data = response.read()
                        root = ET.fromstring(xml_data)
                        items = root.findall('.//item')
                    
                        if items:
                            for item in items[:10]:
                                title = item.find('title').text if item.find('title') is not None else "No Title"
                                link = item.find('link').text if item.find('link') is not None else "#"
                                source_elem = item.find('source')
                                publisher = source_elem.text if source_elem is not None else "Google News"
                            
                                pub_time = item.find('pubDate').text if item.find('pubDate') is not None else ""
                                time_str = ""
                                if pub_time:
                                    try:
                                        dt = parsedate_to_datetime(pub_time)
                                        jst_dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
                                        time_str = f" ({jst_dt.strftime('%Y-%m-%d %H:%M')})"
                                    except Exception:
                                        time_str = f" ({pub_time})"
                                    
                                st.markdown(f"- [{title}]({link}) - *{publisher}*{time_str}")
                        else:
                            st.info("関連ニュースは見つかりませんでした。")
                except Exception as e:
                    st.warning(f"ニュースの取得中にエラーが発生しました: {e}")

        if btn_country_ai:
            if not api_key:
                st.warning("APIキーを設定してください。")
            else:
                with st.spinner(f"Cheyanneが{selected_country}の経済情報を分析中..."):
                    prompt = f"""
    あなたはプロのマクロ経済アナリストです。
    現在の「{selected_country}」の最新の経済状況について、俯瞰的かつ詳細に解説してください。

    以下の要素を含めて、箇条書きでわかりやすく出力してください：
    1. **マクロ経済環境の現状**（インフレ動向、GDP成長率の推移目安、雇用情勢など）
    2. **現在の金融政策と金利動向**（中央銀行のスタンスなど）
    3. **主要な産業トレンドや特徴**
    4. **経済における主要なリスクや足元の注目イベント**
    """
                    try:
                        res = client.models.generate_content(
                            model=model_choice,
                            contents=prompt
                        )
                        st.success(f"🤖 {selected_country}の経済分析")
                        st.markdown(res.text)
                    except Exception as e:
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                            st.error("APIの利用制限 (429) に達しました。モデルをFlashに変更してください。")
                        else:
                            st.error(f"取得失敗: {e}")

        if btn_country_adr:
            if not api_key:
                st.warning("APIキーを設定してください。")
            else:
                with st.spinner(f"Cheyanneが{selected_country}を拠点とする米国上場企業を選定中..."):
                    prompt = f"""
    あなたはプロの証券アナリストです。
    「{selected_country}」に本社または主要な拠点を置いており、かつ米国の株式市場（NYSE, NASDAQなど）で取引可能な（ADRを含む）おすすめの企業を最大3社厳選してください。

    出力は以下のJSON配列形式のみで行ってください。コードは必須で米国のティッカーシンボル（例: TSM, ASMLなど）としてください。もし対象国から米国に上場している企業が見つからない場合や不明な場合は、空の配列 `[]` を出力してください。選定理由は、主力事業や強みを踏まえて100字程度で記述してください。

    ```json
    [
      {{
        "code": "ASML",
        "name": "ASML Holding N.V.",
        "reason": "選定理由(100字程度)"
      }}
    ]
    ```
    """
                    try:
                        res = client.models.generate_content(
                            model=model_choice,
                            contents=prompt
                        )
                        st.session_state.country_adr_text = res.text
                    except Exception as e:
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                            st.error("APIの利用制限 (429) に達しました。モデルをFlashに変更してください。")
                        else:
                            st.error(f"取得失敗: {e}")

        # JSONパースして関連企業を表示
        if "country_adr_text" in st.session_state:
            import json
            import re
            text = st.session_state.country_adr_text
            match = re.search(r'\[.*\]', text, flags=re.DOTALL)
            if match:
                try:
                    recs = json.loads(match.group(0))
                    if not recs:
                        st.info(f"{selected_country}を拠点とするおすすめの米国上場企業は見つかりませんでした。")
                    else:
                        st.success(f"🏢 {selected_country}拠点の米国上場企業")
                        cols = st.columns(3)
                        for i, rec in enumerate(recs):
                            with cols[i % 3]:
                                st.markdown(f"**{rec.get('name')}** ({rec.get('code')})")
                                st.caption(rec.get('reason'))
                                st.button("この銘柄を分析", key=f"country_adr_btn_{rec.get('code')}_{selected_country}_{i}", on_click=set_ticker, args=(rec.get('code'),))
                except Exception as e:
                    st.write(text)
            else:
                st.write(text)

    st.markdown("---")

    # おすすめ銘柄セクション
    with st.expander("✨ Cheyanneが選ぶ！今日の注目・おすすめ銘柄", expanded=False):
        if not api_key:
            st.warning("APIキーを設定してください。")
        else:
            st.write("▼ 個別銘柄のおすすめ")
            col_n1, col_n2 = st.columns(2)
            with col_n1:
                btn_jp_stock = st.button("🇯🇵 おすすめ日本株", key="gen_jp_stock", use_container_width=True)
            with col_n2:
                btn_us_stock = st.button("🇺🇸 おすすめ米国株", key="gen_us_stock", use_container_width=True)
            
            st.write("▼ ETF (上場投資信託) のおすすめ")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                btn_jp_etf = st.button("🇯🇵 おすすめ東証ETF", key="gen_jp_etf", use_container_width=True)
            with col_e2:
                btn_us_etf = st.button("🇺🇸 おすすめ米国ETF", key="gen_us_etf", use_container_width=True)

            selected_action = None
            if btn_jp_stock: selected_action = "jp_stock"
            elif btn_us_stock: selected_action = "us_stock"
            elif btn_jp_etf: selected_action = "jp_etf"
            elif btn_us_etf: selected_action = "us_etf"

            if selected_action:
                spinner_msg = "Cheyanneが情報を分析しておすすめを選定中..."
                with st.spinner(spinner_msg):
                    try:
                        if selected_action == "jp_stock":
                            prompt = "あなたはプロの証券アナリストです。現在の日本のマクロ経済や本日の市場環境を踏まえ、本日注目すべき日本の個別銘柄を日本の株から3つ厳選してください。\n出力は以下のJSON配列形式のみで行ってください。コードは必ず4桁の数字としてください。\n\n```json\n[\n  {\n    \"code\": \"7203\",\n    \"name\": \"トヨタ自動車\",\n    \"reason\": \"選定理由(100字程度)\"\n  }\n]\n```"
                        elif selected_action == "us_stock":
                            prompt = "あなたはプロの証券アナリストです。現在のマクロ経済環境を踏まえ、本日注目すべき米国・海外の個別銘柄を3つ厳選してください。\n出力は以下のJSON配列形式のみで行ってください。コードはティッカーシンボルとしてください。\n\n```json\n[\n  {\n    \"code\": \"AAPL\",\n    \"name\": \"Apple Inc.\",\n    \"reason\": \"選定理由(100字程度)\"\n  }\n]\n```"
                        elif selected_action == "jp_etf":
                            prompt = "あなたはプロの証券アナリストです。現在の日本のマクロ経済や本日の市場環境を踏まえ、本日注目すべき日本の東証上場ETFを3つ厳選してください。\n出力は以下のJSON配列形式のみで行ってください。コードは必ず4桁の数字としてください。\n\n```json\n[\n  {\n    \"code\": \"1321\",\n    \"name\": \"NF・日経225 ETF\",\n    \"reason\": \"選定理由(100字程度)\"\n  }\n]\n```"
                        elif selected_action == "us_etf":
                            prompt = "あなたはプロの証券アナリストです。現在の世界情勢やグローバルなマクロ経済環境を踏まえ、今後伸びそうな有望な米国上場ETFを3つ厳選してください。\n選定理由は、具体的にどのような世界情勢（金利動向、地政学リスク、特定の産業トレンドなど）が背景にあるのかを明らかにして100字程度で記述してください。\n出力は以下のJSON配列形式のみで行ってください。コードはティッカーシンボル（SPYなど）としてください。\n\n```json\n[\n  {\n    \"code\": \"SPY\",\n    \"name\": \"SPDR S&P 500 ETF Trust\",\n    \"reason\": \"選定理由(世界情勢と絡めた理由を100字程度)\"\n  }\n]\n```"

                        res = client.models.generate_content(
                            model=model_choice,
                            contents=prompt
                        )
                        st.session_state.daily_recommendation_text = res.text
                    except Exception as e:
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                            st.error("APIの利用制限 (429) に達しました。モデルをFlashに変更してください。")
                        else:
                            st.error(f"取得失敗: {e}")
                        
            # パースして表示
            if "daily_recommendation_text" in st.session_state:
                import json
                import re
                text = st.session_state.daily_recommendation_text
                match = re.search(r'\[.*\]', text, flags=re.DOTALL)
                if match:
                    try:
                        recs = json.loads(match.group(0))
                        cols = st.columns(3)
                        for i, rec in enumerate(recs):
                            with cols[i % 3]:
                                st.markdown(f"**{rec.get('name')}** ({rec.get('code')})")
                                st.caption(rec.get('reason'))
                                st.button("この銘柄を分析", key=f"rec_btn_{rec.get('code')}", on_click=set_ticker, args=(rec.get('code'),))
                    except Exception as e:
                        st.write(text) # パース失敗時はそのまま表示
                else:
                    st.write(text)

    st.markdown("---")

with tab_analysis:
    # 指数クイックボタン
    st.write("🌍 **主要指数クイック分析**")
    qcol1, qcol2, qcol3, qcol4, qcol5 = st.columns(5)
    with qcol1: st.button("日経平均", key="q_n225", on_click=set_ticker, args=("^N225",), use_container_width=True)
    with qcol2: st.button("S&P 500", key="q_gspc", on_click=set_ticker, args=("^GSPC",), use_container_width=True)
    with qcol3: st.button("NASDAQ", key="q_ixic", on_click=set_ticker, args=("^IXIC",), use_container_width=True)
    with qcol4: st.button("TOPIX", key="q_topx", on_click=set_ticker, args=("^TOPX",), use_container_width=True)
    with qcol5: st.button("ドル円", key="q_jpy", on_click=set_ticker, args=("JPY=X",), use_container_width=True)

    # 銘柄コードと表示期間の入力
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if market_choice == "日本":
            ticker_placeholder = "東証のETFコードを入力してください（例: 1321 日経225連動型）" if st.session_state.get("etf_mode", False) else "東証の銘柄コードを入力してください（例: 7203 トヨタ自動車）"
        else:
            ticker_placeholder = "米国のETFティッカーを入力してください（例: SPY, VOO）" if st.session_state.get("etf_mode", False) else "米国のティッカーを入力してください（例: AAPL, MSFT）"
        st.text_input(ticker_placeholder, key="ticker_widget")
        ticker_input = st.session_state.ticker_widget
    with col2:
        period_options = {"1週間": "1wk", "1ヶ月": "1mo", "3ヶ月": "3mo", "半年": "6mo", "1年": "1y", "3年": "3y", "5年": "5y", "最大": "max"}
        period_label = st.selectbox("表示期間", list(period_options.keys()), index=1)
        selected_period = period_options[period_label]
    with col3:
        interval_options = {"日足": "1d", "週足": "1wk", "月足": "1mo"}
        interval_label = st.selectbox("足の種類", list(interval_options.keys()), index=0)
        selected_interval = interval_options[interval_label]

    if ticker_input:
        ticker_input_str = str(ticker_input).upper().strip()
        import re
    
        # ティッカー形式から日本/米国を自動判別
        if ticker_input_str.endswith(".T"):
            ticker_symbol = ticker_input_str
            is_japan_market = True
        elif re.match(r'^\d[A-Z0-9]{3}$', ticker_input_str):
            # 4桁で先頭が数字の場合は日本の証券コード（例: 7203, 130A）とみなす
            ticker_symbol = f"{ticker_input_str}.T"
            is_japan_market = True
        elif re.match(r'^[A-Z]{1,5}$', ticker_input_str) and not ticker_input_str.isdigit():
            # アルファベット主体は米国/海外ティッカー
            ticker_symbol = ticker_input_str
            is_japan_market = False
        else:
            # 判別が難しい場合はラジオボタンの選択に依存
            if market_choice == "日本":
                ticker_symbol = f"{ticker_input_str}.T"
                is_japan_market = True
            else:
                ticker_symbol = ticker_input_str
                is_japan_market = False
            
        st.write(f"証券コード/ティッカー: {ticker_symbol} のデータを取得しています...")
    
        try:
            # yfinanceでデータを取得
            ticker = yf.Ticker(ticker_symbol)
        
            # 指定された期間と間隔のデータを取得
            hist = ticker.history(period=selected_period, interval=selected_interval)
        
            if hist.empty:
                st.warning("データが取得できませんでした。正しい4桁の銘柄コードを入力してください。")
            else:
                info = ticker.info
                is_index = info.get('quoteType') == 'INDEX' or ticker_symbol.startswith('^') or ticker_symbol.endswith('=X')
                company_name = info.get('longName', info.get('shortName', str(ticker_input)))
            
                # 検索履歴の更新 (同じコードがあれば削除してから追加)
                st.session_state.search_history = [item for item in st.session_state.search_history if item[0] != ticker_input]
                st.session_state.search_history.append((ticker_input, company_name))
            
                # 一番上の表示とお気に入りトグル
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.subheader(f"📊 {company_name} ({ticker_input})")
                with c2:
                    is_fav = any(item[0] == ticker_input for item in st.session_state.favorites)
                    def toggle_favorite():
                        if is_fav:
                            st.session_state.favorites = [item for item in st.session_state.favorites if item[0] != ticker_input]
                        else:
                            st.session_state.favorites.append((ticker_input, company_name))
                        save_favorites()
                
                    button_label = "★ お気に入り解除" if is_fav else "☆ お気に入り追加"
                    st.button(button_label, key=f"fav_toggle_{ticker_input}", on_click=toggle_favorite)
                
                # --- 主要指標の表示 ---
                if is_index:
                    st.write("**主要市場指標（インデックス情報）**")
                else:
                    st.write("**主要指標（ファンダメンタルズ）**")
            
                # データの準備
                current_price = info.get('currentPrice') or info.get('regularMarketPrice') or (hist['Close'].iloc[-1] if not hist.empty else 0)
                target_mean = info.get('targetMeanPrice')
                rec_key = info.get('recommendationKey', 'N/A').upper().replace('_', ' ')
                pe_val = info.get('trailingPE', info.get('forwardPE', 'N/A'))

                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            
                market_cap = info.get('marketCap', 'N/A')
                if market_cap != 'N/A' and market_cap is not None:
                    market_cap = f"{market_cap / 100000000:,.0f}億円"
                else:
                    market_cap = "---"
                
                per = info.get('trailingPE', info.get('forwardPE', 'N/A'))
                if per != 'N/A' and per is not None:
                    per = f"{per:.2f}倍"
                else:
                    per = "---"
                
                pbr = info.get('priceToBook', 'N/A')
                if pbr != 'N/A' and pbr is not None:
                    pbr = f"{pbr:.2f}倍"
                else:
                    pbr = "---"
                
                # 確実に「小数（0.028等）」として取得できる trailingAnnualDividendYield を利用して表示ミスを防ぐ
                div_yield_val = info.get('trailingAnnualDividendYield', info.get('dividendYield', 'N/A'))
                if div_yield_val != 'N/A' and div_yield_val is not None:
                    # もし取得した値がすでにパーセンテージ化されている（1.0より大きいなど）場合への対策
                    if div_yield_val > 1.0:
                        div_yield = f"{div_yield_val:.2f}%"
                    else:
                        div_yield = f"{div_yield_val * 100:.2f}%"
                else:
                    div_yield = "---"
                
                if st.session_state.get("etf_mode", False):
                    m_col1.metric("純資産総額(目安)", market_cap)
                    m_col2.metric("PER(参考)", per)
                    m_col3.metric("PBR(参考)", pbr)
                    m_col4.metric("分配金利回り", div_yield)
                else:
                    m_col1.metric("時価総額", market_cap)
                    m_col2.metric("PER(株価収益率)", per)
                    m_col3.metric("PBR(株価純資産倍率)", pbr)
                    m_col4.metric("配当利回り", div_yield)
                
                # 追加：52週高値・安値
                high52 = info.get('fiftyTwoWeekHigh', 'N/A')
                low52 = info.get('fiftyTwoWeekLow', 'N/A')
                if high52 != 'N/A' and high52 is not None:
                    high52 = f"{high52:,.1f}" if isinstance(high52, (int, float)) else str(high52)
                else:
                    high52 = "---"
                
                if low52 != 'N/A' and low52 is not None:
                    low52 = f"{low52:,.1f}" if isinstance(low52, (int, float)) else str(low52)
                else:
                    low52 = "---"

                # 業種・セクター
                sector = info.get('sector', '---')
                industry = info.get('industry', '---')
                
                m_col5, m_col6, m_col7, m_col8 = st.columns(4)
                if is_index:
                    m_col1.metric("52週高値", high52)
                    m_col2.metric("52週安値", low52)
                    m_col3.metric("現在値", f"{current_price:,.2f}")
                    m_col4.metric("通貨", info.get('currency', '---'))
                    m_col5.metric("50日移動平均", f"{info.get('fiftyDayAverage', 0):,.1f}")
                    m_col6.metric("200日移動平均", f"{info.get('twoHundredDayAverage', 0):,.1f}")
                    m_col7.metric("取引市場", info.get('exchange', '---'))
                    m_col8.metric("種類", "インデックス/通貨" if not ticker_symbol.endswith('=X') else "為替")
                elif st.session_state.get("etf_mode", False):
                    m_col5.metric("52週高値", high52)
                    m_col6.metric("52週安値", low52)
                    m_col7.metric("アセットクラス", info.get('category', '---'))
                    m_col8.metric("ファミリ", info.get('fundFamily', '---'))
                else:
                    m_col5.metric("52週高値", high52)
                    m_col6.metric("52週安値", low52)
                    m_col7.metric("セクター", sector)
                    m_col8.metric("業種", industry)
                
                # --- 🚀 プレミアム診断ダッシュボード ---
                st.subheader("🚀 Cheyanne プレミアム診断")
                
                # データの準備(移動済み)

                
                # RSIの計算
                diag_delta = hist['Close'].diff()
                diag_up = diag_delta.clip(lower=0); diag_down = -1 * diag_delta.clip(upper=0)
                diag_ema_up = diag_up.ewm(com=13, adjust=False).mean(); diag_ema_down = diag_down.ewm(com=13, adjust=False).mean()
                diag_rs = diag_ema_up / diag_ema_down
                diag_latest_rsi = 100 - (100 / (1 + diag_rs.iloc[-1])) if not diag_rs.empty else 50

                # 追加指標：25日乖離率と出来高変化
                ma25 = hist['Close'].rolling(window=25).mean()
                deviation25 = ((hist['Close'].iloc[-1] - ma25.iloc[-1]) / ma25.iloc[-1] * 100) if not ma25.empty else 0
                vol_factor = (hist['Volume'].iloc[-1] / hist['Volume'].rolling(20).mean().iloc[-1]) if not hist['Volume'].empty else 1
                
                # 需給データ
                short_ratio = info.get('shortRatio', 'N/A')
                inst_held = info.get('heldPercentInstitutions', 0) * 100

                d_col1, d_col2, d_col3 = st.columns([1.2, 1, 1.2])

                with d_col1:
                    st.markdown("##### 🕵️ 需給・大口動向")
                    st.metric("機関投資家保有比率", f"{inst_held:.1f}%")
                    st.write(f"ショート比率: **{short_ratio}**")
                    vol_status = "🔥 出来高急増" if vol_factor > 2 else "⚖️ 平常"
                    st.write(f"出来高変化: {vol_factor:.2f}倍 ({vol_status})")

                with d_col2:
                    st.markdown("##### 🌡️ テクニカル診断")
                    gauge_color = "#d62728" if diag_latest_rsi > 70 else "#1f77b4" if diag_latest_rsi < 30 else "#2ca02c"
                    fig_g = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = diag_latest_rsi,
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        gauge = {
                            'axis': {'range': [0, 100]},
                            'bar': {'color': gauge_color},
                            'threshold': {'line': {'color': "black", 'width': 4}, 'value': diag_latest_rsi}
                        }
                    ))
                    fig_g.update_layout(height=180, margin=dict(l=20, r=20, t=20, b=0))
                    st.plotly_chart(fig_g, use_container_width=True)
                    st.markdown(f"<div style='text-align:center; font-weight:bold;'>25日乖離: {deviation25:+.2f}%</div>", unsafe_allow_html=True)

                with d_col3:
                    st.markdown("##### 📊 投資コンセンサス")
                    # 判定ラベル
                    badge_color = "#d62728" if "SELL" in rec_key else "#2ca02c" if "BUY" in rec_key else "#7f7f7f"
                    st.markdown(f"""<div style="background-color: {badge_color}; color: white; padding: 10px; border-radius: 8px; text-align: center; font-weight: bold;">{rec_key}</div>""", unsafe_allow_html=True)
                    if target_mean and current_price:
                        upside = (target_mean - current_price) / current_price * 100
                        st.metric("期待アップサイド", f"{upside:+.1f}%")
                    st.write(f"セクター: **{sector}**")

                # --- 目標株価と競合比較 ---
                a_col1, a_col2 = st.columns(2)
                with a_col1:
                    if target_mean:
                        st.markdown("##### 🎯 ターゲット価格推移")
                        t_low = info.get('targetLowPrice', current_price*0.8)
                        t_high = info.get('targetHighPrice', current_price*1.2)
                        st.write(f"現在価格: **¥{current_price:,.0f}** (USD銘柄は換算済)")
                        fig_t = go.Figure()
                        fig_t.add_trace(go.Bar(x=['安値', '平均', '高値'], y=[t_low, target_mean, t_high], marker_color=['#bdc3c7', '#f1c40f', '#e67e22']))
                        fig_t.add_hline(y=current_price, line_dash="dash", line_color="red", annotation_text="現在株価")
                        fig_t.update_layout(height=250, margin=dict(t=20, b=20))
                        st.plotly_chart(fig_t, use_container_width=True)
                    else:
                        st.info("アナリストの目標株価データはありません。")

                with a_col2:
                    st.markdown("##### 👥 市場・競合分析")
                    st.caption(f"セクター: {sector} / 業界: {industry}")
                    st.write(f"**{company_name}** は現在の水準で、同業他社と比較して割安感があるか、Cheyanneの分析を確認しましょう。")
                    if pe_val: st.write(f"現在のPER: **{pe_val:.1f}倍**")

                # --- 🤖 Cheyanne Pro 深層診断レポート ---
                st.divider()
                if not api_key:
                    st.warning("深層診断レポートを利用するにはAPIキーを設定してください。")
                else:
                    deep_prompt = f"""
あなたは伝説的な投資プランナーであり、心理分析を得意とするクオンツ「Cheyanne」です。
以下の精緻なデータに基づき、この銘柄の情報の裏側を読み解く【深層戦略レポート】を作成してください。

【銘柄】: {company_name} ({ticker_symbol})
【テクニカル】: RSI={diag_latest_rsi:.1f}, 25日乖離={deviation25:.2f}%, 出来高変化={vol_factor:.2f}倍
【需給・大口動向】: ショート比率={short_ratio}, 機関投資家保有={inst_held:.1f}%
【基本/コンセンサス】: PER={pe_val}, 推奨={rec_key}

【指示事項】:
1. **テクニカル・ジャッジ**: 指標の過熱感と現在のトレンドの持続性をプロの視点で評価。
2. **市場心理と大口の意図**: 出来高や空売り状況から、市場参加者が今何を考え、大口がどのアクション（仕込み・逃げ）をとっているか推論。
3. **機関投資家の戦略**: セクター全体の状況と保有比率を照らし合わせ、将来的な需給の改善や悪化の予兆を鋭く指摘。
4. **統合投資戦略**: 目先のノイズに惑わされないための、具体的な投資姿勢を助言。

Markdown形式で、客観的でありながら鋭い洞察を含めて出力してください。
"""
                    try:
                        with st.spinner("Cheyanneが市場の深層を解析中..."):
                            res_deep = safe_generate_content(client, model_choice, deep_prompt)
                            st.markdown(res_deep.text)
                    except Exception as e:
                        st.error(f"深層分析中にエラーが発生しました: {e}")

                st.divider()

                # 取得したデータの表示
                st.subheader(f"過去{period_label}の株価詳細チャート")
            
                from plotly.subplots import make_subplots

                # テクニカル指標とベンチマークの選択
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    tech_indicators = st.multiselect(
                        "表示するテクニカル指標を選択してください:",
                        ["SMA (5日)", "SMA (25日)", "SMA (75日)", "ボリンジャーバンド (25日)", "RSI (14日)", "MACD"],
                        default=[]
                    )
                with col_i2:
                    benchmark_options = {"なし": None, "日経平均 (^N225)": "^N225", "S&P500 (^GSPC)": "^GSPC", "TOPIX (1306.T)": "1306.T", "NASDAQ (^IXIC)": "^IXIC"}
                    benchmark_label = st.selectbox("比較するベンチマーク:", list(benchmark_options.keys()), index=0)
                    selected_benchmark = benchmark_options[benchmark_label]
            
                # 日本市場と米国市場でローソク足の色を一般的に使われる色に切り替える
                if is_japan_market:
                    increasing_color = '#ff4b4b' # 赤
                    decreasing_color = '#1f77b4' # 青
                else:
                    increasing_color = '#2ca02c' # 緑
                    decreasing_color = '#d62728' # 赤

                fig = make_subplots(specs=[[{"secondary_y": True}]])
                
                fig.add_trace(go.Candlestick(
                    x=hist.index,
                    open=hist['Open'],
                    high=hist['High'],
                    low=hist['Low'],
                    close=hist['Close'],
                    increasing_line_color=increasing_color,
                    decreasing_line_color=decreasing_color,
                    name='ローソク足'
                ), secondary_y=False)
            
                # 土日などの休場日をチャートのギャップとして表示させない
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
            
                # SMA (5日)
                if "SMA (5日)" in tech_indicators:
                    sma_5 = hist['Close'].rolling(window=5).mean()
                    fig.add_trace(go.Scatter(x=hist.index, y=sma_5, mode='lines', name='SMA (5日)', line=dict(color='#1f77b4', width=1.5)))
                
                # SMA (25日)
                if "SMA (25日)" in tech_indicators:
                    sma_25 = hist['Close'].rolling(window=25).mean()
                    fig.add_trace(go.Scatter(x=hist.index, y=sma_25, mode='lines', name='SMA (25日)', line=dict(color='#ff7f0e', width=1.5)))
                
                # SMA (75日)
                if "SMA (75日)" in tech_indicators:
                    sma_75 = hist['Close'].rolling(window=75).mean()
                    fig.add_trace(go.Scatter(x=hist.index, y=sma_75, mode='lines', name='SMA (75日)', line=dict(color='#2ca02c', width=1.5)))

                # ボリンジャーバンド (25日)
                if "ボリンジャーバンド (25日)" in tech_indicators:
                    sma_25 = hist['Close'].rolling(window=25).mean()
                    std_25 = hist['Close'].rolling(window=25).std()
                    bb_upper = sma_25 + 2 * std_25
                    bb_lower = sma_25 - 2 * std_25
                
                    # 上部バンド
                    fig.add_trace(go.Scatter(
                        x=hist.index, y=bb_upper, mode='lines', 
                        name='BB +2σ', line=dict(color='rgba(214, 39, 40, 0.5)', width=1, dash='dot')
                    ))
                    # 下部バンド (上部バンドからの塗りつぶし)
                    fig.add_trace(go.Scatter(
                        x=hist.index, y=bb_lower, mode='lines', 
                        name='BB -2σ', line=dict(color='rgba(214, 39, 40, 0.5)', width=1, dash='dot'),
                        fill='tonexty', fillcolor='rgba(214, 39, 40, 0.1)'
                    ), secondary_y=False)

                # ベンチマークの追加
                if selected_benchmark:
                    try:
                        bench_ticker = yf.Ticker(selected_benchmark)
                        bench_hist = bench_ticker.history(period=selected_period, interval=selected_interval)
                        if not bench_hist.empty:
                            fig.add_trace(go.Scatter(
                                x=bench_hist.index, y=bench_hist['Close'], mode='lines', 
                                name=f'{benchmark_label}', line=dict(color='rgba(128, 0, 128, 0.7)', width=2, dash='dash')
                            ), secondary_y=True)
                    except Exception as e:
                        pass # 無視

                fig.update_layout(
                    xaxis_rangeslider_visible=False,
                    margin=dict(l=0, r=0, t=50, b=0),
                    height=400,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                # 第二Y軸の設定（グリッド線を消すなど）
                fig.update_yaxes(title_text="株価", secondary_y=False)
                if selected_benchmark:
                    fig.update_yaxes(showgrid=False, secondary_y=True)

                st.plotly_chart(fig, use_container_width=True)
                
                # RSIの描画
                if "RSI (14日)" in tech_indicators:
                    delta = hist['Close'].diff()
                    up = delta.clip(lower=0)
                    down = -1 * delta.clip(upper=0)
                    ema_up = up.ewm(com=13, adjust=False).mean()
                    ema_down = down.ewm(com=13, adjust=False).mean()
                    rs = ema_up / ema_down
                    rsi = 100 - (100 / (1 + rs))
                    
                    fig_rsi = go.Figure()
                    fig_rsi.add_trace(go.Scatter(x=hist.index, y=rsi, mode='lines', name='RSI(14)', line=dict(color='#8c564b', width=1.5)))
                    fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="買われすぎ (70)")
                    fig_rsi.add_hline(y=30, line_dash="dash", line_color="blue", annotation_text="売られすぎ (30)")
                    fig_rsi.update_layout(height=200, margin=dict(l=0, r=0, t=30, b=0), yaxis_title="RSI", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig_rsi, use_container_width=True)

                # MACDの描画
                if "MACD" in tech_indicators:
                    exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
                    exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
                    macd_line = exp1 - exp2
                    signal_line = macd_line.ewm(span=9, adjust=False).mean()
                    macd_hist = macd_line - signal_line
                    
                    fig_macd = go.Figure()
                    # ヒストグラムは正負で色を変える
                    colors = ['#2ca02c' if val >= 0 else '#d62728' for val in macd_hist]
                    fig_macd.add_trace(go.Bar(x=hist.index, y=macd_hist, name='Histogram', marker_color=colors))
                    fig_macd.add_trace(go.Scatter(x=hist.index, y=macd_line, mode='lines', name='MACD', line=dict(color='#1f77b4', width=1.5)))
                    fig_macd.add_trace(go.Scatter(x=hist.index, y=signal_line, mode='lines', name='Signal', line=dict(color='#ff7f0e', width=1.5)))
                    fig_macd.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0), yaxis_title="MACD", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig_macd, use_container_width=True)
                
                # --- 財務ハイライト表示 (ETF以外) ---
                if not st.session_state.get("etf_mode", False):
                    st.divider()
                    st.write("**🏢 財務ハイライト (売上・純利益)**")
                    try:
                        financials_df = ticker.financials
                        if not financials_df.empty:
                            rev = financials_df.loc['Total Revenue'] if 'Total Revenue' in financials_df.index else None
                            net = financials_df.loc['Net Income'] if 'Net Income' in financials_df.index else None
                            
                            if rev is not None and net is not None:
                                rev = rev.dropna().iloc[::-1]
                                net = net.dropna().iloc[::-1]
                                
                                fig_fin = go.Figure()
                                fig_fin.add_trace(go.Bar(x=[str(d.year) for d in rev.index], y=rev.values, name='売上高', marker_color='#1f77b4'))
                                fig_fin.add_trace(go.Bar(x=[str(d.year) for d in net.index], y=net.values, name='純利益', marker_color='#ff7f0e'))
                                
                                fig_fin.update_layout(barmode='group', margin=dict(l=0, r=0, t=30, b=0), height=300, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                                st.plotly_chart(fig_fin, use_container_width=True)
                            else:
                                st.caption("この銘柄の財務データは取得できませんでした。")
                    except Exception as e:
                        st.caption("財務データの取得に失敗しました。")
            
                # --- 配当履歴の表示 ---
                try:
                    div_data = ticker.dividends
                    if not div_data.empty:
                        # 直近5年分程度のデータを表示するように絞る
                        recent_div = div_data.tail(20)  # 四半期配当なら5年分程度
                        st.divider()
                        st.write("**💰 配当履歴**")
                        fig_div = go.Figure()
                        fig_div.add_trace(go.Bar(x=recent_div.index, y=recent_div.values, marker_color='#2ca02c', name="配当金"))
                        fig_div.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0), xaxis_title="権利落ち日", yaxis_title="配当額")
                        st.plotly_chart(fig_div, use_container_width=True)
                except Exception as e:
                    pass

                with st.expander("詳細データ（株価）を見る"):
                    st.dataframe(hist)
                
                st.divider()
            
                # --- 関連ニュースの表示 ---
                st.subheader("📰 関連ニュース")
            
                # Google NewsのRSSを使用して日本語ニュースを取得する
                import urllib.request
                import urllib.parse
                import xml.etree.ElementTree as ET
                from email.utils import parsedate_to_datetime
                import datetime
            
                # 企業名を取得して検索クエリにする (情報が取れない場合はコード)
                search_query = ticker.info.get('longName', ticker.info.get('shortName', ticker_input))
                encoded_query = urllib.parse.quote(search_query)
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
            
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        xml_data = response.read()
                        root = ET.fromstring(xml_data)
                        items = root.findall('.//item')
                    
                        if items:
                            for item in items[:5]:
                                title = item.find('title').text if item.find('title') is not None else "No Title"
                                link = item.find('link').text if item.find('link') is not None else "#"
                                source_elem = item.find('source')
                                publisher = source_elem.text if source_elem is not None else "Google News"
                            
                                pub_time = item.find('pubDate').text if item.find('pubDate') is not None else ""
                                time_str = ""
                                if pub_time:
                                    try:
                                        dt = parsedate_to_datetime(pub_time)
                                        # 日本時間(JST)に変換して表示
                                        jst_dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
                                        time_str = f" ({jst_dt.strftime('%Y-%m-%d %H:%M')})"
                                    except Exception:
                                        time_str = f" ({pub_time})"
                                    
                                st.markdown(f"- [{title}]({link}) - *{publisher}*{time_str}")
                        else:
                            st.info("直近の関連ニュースは見つかりませんでした。")
                except Exception as e:
                    st.warning(f"ニュースの取得中に一時的なエラーが発生しました。")
            
                st.divider()
            
                # --- 対象国の経済・マクロ環境分析 ---
                st.subheader("🌍 対象国の経済・マクロ環境分析")
                if api_key:
                    st.markdown(f"**{company_name}** に関連する国・地域の経済状況を分析します。（インフレ動向、金利、景況感など）")
                    macro_state_key = f"macro_{ticker_symbol}"
                
                    if st.button(f"🌍 {company_name} の対象エリア経済情報をCheyanneに分析させる"):
                        with st.spinner("Cheyanneが経済・マクロ情報を分析中..."):
                            macro_prompt = f"""
    あなたはプロのマクロ経済アナリストです。
    以下の銘柄/ETF（{company_name}, コード: {ticker_input}）の主な投資対象国・地域を特定し、そのエリアの現在の経済状況について解説してください。

    以下の要素を含めて、簡潔に箇条書きで解説してください：
    1. **主要な対象国・地域** (解説の前提となるエリアを明記してください)
    2. **現在の金融政策と金利動向** (中央銀行のスタンスなど)
    3. **インフレ・景況感の現状**
    4. **マクロ経済における主要なリスクや注目イベント**
    """
                            try:
                                res_macro = client.models.generate_content(
                                    model=model_choice,
                                    contents=macro_prompt
                                )
                                st.session_state[macro_state_key] = res_macro.text
                            except Exception as e:
                                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                                    st.error("⚠️ APIの利用制限 (429) に達しました。")
                                else:
                                    st.error(f"エラーが発生しました: {e}")
                
                    if macro_state_key in st.session_state:
                        st.info(st.session_state[macro_state_key])
                else:
                    st.info("APIキーが設定されていないため実行できません。")

                # --- 📊 グローバル指数比較チャート (Index Only) ---
                if is_index:
                    st.subheader("🌍 グローバル市場との相関・騰落率比較")
                    with st.spinner("グローバルデータを集計中..."):
                        try:
                            compare_indices = {
                                "日経平均": "^N225", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", 
                                "欧州STOXX50": "^STOXX50E", "ドル円": "JPY=X"
                            }
                            # 本人（検索中指数）も確実にグラフに含めるため上書き/追加
                            compare_indices[company_name] = ticker_symbol
                            
                            comp_data = yf.download(list(compare_indices.values()), period=selected_period)["Close"]
                            comp_norm = comp_data / comp_data.iloc[0] * 100
                            
                            fig_comp = go.Figure()
                            for label, sym in compare_indices.items():
                                if sym in comp_norm.columns:
                                    width = 4 if sym == ticker_symbol else 2
                                    fig_comp.add_trace(go.Scatter(x=comp_norm.index, y=comp_norm[sym], name=label, line=dict(width=width)))
                            
                            fig_comp.update_layout(height=400, margin=dict(t=30, b=20), yaxis_title="騰落率 (%) 100=開始時", hovermode="x unified")
                            st.plotly_chart(fig_comp, use_container_width=True)
                            st.caption("※ 期間開始時を100とした相対比較。為替（ドル円）は円安＝上昇として表示されます。")
                        except:
                            st.info("比較データの取得に失敗しました。")

                st.divider()
            
                # --- 📊 業績ダイジェスト (Financial Highlights) ---
                if not is_index:
                    st.subheader("📊 業績・財務の推移")
                    try:
                        fin = ticker.financials
                        if not fin.empty and 'Total Revenue' in fin.index:
                            # 2024-09-30 のような形式を年に直す
                            fin_years = [str(d.year) for d in fin.columns]
                            revenue = fin.loc['Total Revenue'].values / 1e8 # 単位: 億円または憶ドル
                            net_income = fin.loc['Net Income'].values / 1e8 if 'Net Income' in fin.index else None
                            
                            fig_fin = go.Figure()
                            fig_fin.add_trace(go.Bar(x=fin_years, y=revenue, name="売上高", marker_color="royalblue"))
                            if net_income is not None:
                                fig_fin.add_trace(go.Bar(x=fin_years, y=net_income, name="純利益", marker_color="lightgreen"))
                            
                            curr_label = "憶ドル" if not is_japan_market else "億円"
                            fig_fin.update_layout(
                                barmode='group', height=300, 
                                margin=dict(t=30, b=20),
                                yaxis_title=f"金額 ({curr_label})"
                            )
                            st.plotly_chart(fig_fin, use_container_width=True)
                        else:
                            st.info("年次財務データが見つかりませんでした。")
                    except Exception as e:
                        st.caption(f"財務データの取得中にエラーが発生しました。")

                # --- 🗞️ 最新ニュース ---
                st.subheader("🗞️ 最新ニュース")
                try:
                    news_list = ticker.news[:5]
                    if news_list:
                        for i, n in enumerate(news_list):
                            with st.expander(f"📌 {n.get('title')}"):
                                st.write(f"ソース: {n.get('publisher')} | 公開日: {pd.to_datetime(n.get('providerPublishTime'), unit='s').strftime('%Y-%m-%d %H:%M')}")
                                st.markdown(f"[記事全文を読む]({n.get('link')})")
                                if api_key:
                                    if st.button("📰 ニュースを翻訳・要約する", key=f"btn_news_{i}"):
                                        with st.spinner("要約中..."):
                                            news_prompt = f"以下のニュースのタイトルと内容を日本語で要約し、この銘柄へのポジティブ/ネガティブな影響を解説してください。\n\nタイトル: {n.get('title')}\nリンク: {n.get('link')}"
                                            res_news = client.models.generate_content(model=model_choice, contents=news_prompt)
                                            st.info(res_news.text)
                    else:
                        st.info("直近の関連ニュースは見つかりませんでした。")
                except:
                    st.caption("ニュースの取得中にエラーが発生しました。")

                st.divider()
                # --- Cheyanneによる分析とアシスタント ---
                st.subheader("🤖 Cheyanneによる投資ポイント")
                if api_key:
                    try:
                        # 企業名を取得（取得できない場合はコードをそのまま使用）
                        company_info = ticker.info
                        company_name = company_info.get('longName', company_info.get('shortName', str(ticker_input)))
                    
                        # 銘柄が変わった場合などのセッションリセット
                        if "current_ticker" not in st.session_state or st.session_state.current_ticker != ticker_symbol:
                            st.session_state.current_ticker = ticker_symbol
                            st.session_state.initial_analysis = None
                            st.session_state.messages = []
                        
                        # 1. 初回分析の実行と表示
                        if st.session_state.initial_analysis is None:
                            st.info("Cheyanneによる詳細な銘柄分析を行うには、以下のボタンをクリックしてください。")
                            if st.button(f"🤖 {company_name}をCheyanneで分析する"):
                                with st.spinner("Cheyanneが業績予想とトレンドを分析中です..."):
                                    # 直近の株価変動を計算
                                    current_price_val = hist['Close'].iloc[-1]
                                    start_price_val = hist['Close'].iloc[0]
                                    price_change_pct = ((current_price_val - start_price_val) / start_price_val) * 100
                                
                                    if is_index:
                                        prompt = f"""
    あなたは世界的に著名なマクロ戦略家（マクロ・ストラテジスト）です。
    提供された市場データに基づき、この指数（インデックス/為替）の「今後の見立て（将来展望）」をプロフェッショナルな視点で記述してください。

    【指数情報】
    - 銘柄名: {company_name} (コード: {ticker_input})
    - 現在値: {current_price_val:,.2f}
    - 過去{period_label}の騰落率: {price_change_pct:+.2f}% (開始値: {start_price_val:,.1f} -> 現在値: {current_price_val:,.1f})
    - 52週レンジ: {low52} - {high52}

    【指示事項】
    以下の構成で、今後3ヶ月〜1年の見立てを厳格に分析してください：
    1. **現在の市場フェーズとトレンド診断**（中長期的なトレンド、主要な節目の突破状況など）
    2. **主要なマクロ要因の影響分析**（金利、インフレ、地政学、景気動向がこの指数に与える影響）
    3. **今後の強気・弱気シナリオ**（どのような条件で上昇/下落するか、具体的な節目となる価格水準の提示）
    4. **他の市場（為替・債券・他国市場）との関連性と波及効果**
    5. **投資家への戦略的アドバイス・留意点**

    専門的でありながら読みやすいMarkdown形式で、箇条書きを活用して出力してください。
    """
                                    elif st.session_state.get("etf_mode", False):
                                        prompt = f"""
    あなたはプロの証券アナリストです。
    以下のETF（上場投資信託）について、提供された客観的なデータと直近の価格動向を踏まえて、最近の市場トレンドや投資妙味を分析し、「投資ポイント」をわかりやすく提示してください。

    【銘柄情報】
    - 銘柄名: {company_name} (コード: {ticker_input})
    - 純資産あるいは時価総額: {market_cap}
    - 分配金利回り: {div_yield}
    - 過去{period_label}の価格騰落率: {price_change_pct:+.2f}% (開始値: {start_price_val:.1f}円 -> 現在値: {current_price_val:.1f}円)

    【指示事項】
    上記の実際のデータ（利回り、直近のトレンドなど）を分析の根拠に組み入れつつ、以下の構成で出力してください：
    1. **連動指数や投資対象の現在の市場環境**
    2. **このETFに投資するメリットと期待されるリターン**
    3. **投資する上でのリスクや留意点**

    簡潔に、箇条書きを交えながら出力してください。
    """
                                    else:
                                        prompt = f"""
    あなたはプロの証券アナリストです。
    以下の株式銘柄について、提供された客観的な財務データと直近の株価動向を踏まえて、最近の市場トレンドや一般的な今後の業績予想を分析し、「投資ポイント」をわかりやすく提示してください。

    【銘柄情報】
    - 銘柄名: {company_name} (コード: {ticker_input})
    - 時価総額: {market_cap}
    - PER (株価収益率): {per}
    - PBR (株価純資産倍率): {pbr}
    - 配当利回り: {div_yield}
    - 過去{period_label}の株価騰落率: {price_change_pct:+.2f}% (開始値: {start_price_val:.1f}円 -> 現在値: {current_price_val:.1f}円)

    【指示事項】
    実際のデータ（割安性、利回り、直近のトレンドなど）を分析の根拠に組み入れつつ、以下の構成で厳格に出力してください：
    1. **総合診断：買うべきか？売るべきか？**（「強気買い」「押し目買い」「ホールド」「利益確定売り」「静観」のいずれかを冒頭に明記し、その結論に至った決定的な理由を3つ挙げてください）
    2. **テクニカル過熱度の評価**（RSIやボリンジャーバンドの観点から、「買われすぎ」か「売られすぎ」か、今後のリバウンドや反落の可能性を明示してください）
    3. **独自の定量的評価と現在の事業環境** (PERやPBR、利回りから見た評価を含める)
    4. **予想される今後の業績ポイントと強み・競合比較**
    5. **投資する上でのリスクや留意点**

    簡潔に、箇条書きを交えながらプロの視点で出力してください。
    """
                                    try:
                                        response = client.models.generate_content(
                                            model=model_choice,
                                            contents=prompt
                                        )
                                        st.session_state.initial_analysis = response.text
                                        st.rerun()
                                    except Exception as e:
                                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                                            st.error("⚠️ APIの利用制限 (429 RESOURCE_EXHAUSTED) に達しました。短時間のリクエスト過多か、無料枠の上限です。しばらく待つか、サイドバーからモデルを `gemini-2.5-flash` 等に変更してください。")
                                        else:
                                            st.error(f"エラーが発生しました: {e}")
                        else:
                            st.write(st.session_state.initial_analysis)
                        
                            st.divider()
                        
                            # 2. Cheyanne（チャット機能）
                            st.subheader("💬 Cheyanneアシスタント")
                            st.markdown(f"**{company_name}** について、気になることをチャットで質問できます。（例: 「主な競合他社は？」「為替の影響はどう受ける？」）")
                        
                            # 過去のチャットログを表示
                            for message in st.session_state.messages:
                                with st.chat_message(message["role"]):
                                    st.markdown(message["content"])
                                
                            # ユーザーの入力があった場合の処理
                            if prompt_chat := st.chat_input(f"{company_name}について質問する..."):
                                # ユーザー側のメッセージを表示＆保存
                                st.chat_message("user").markdown(prompt_chat)
                                st.session_state.messages.append({"role": "user", "content": prompt_chat})
                            
                                # AI側の返答を生成
                                with st.chat_message("assistant"):
                                    with st.spinner("考え中..."):
                                        # 会話履歴を含めたコンテキスト文字列の作成
                                        chat_context = f"あなたはプロの証券アナリストです。現在の話題は「{company_name} (コード: {ticker_input})」です。\n"
                                        chat_context += f"過去の分析内容: {st.session_state.initial_analysis}\n\nこれまでの会話:\n"
                                    
                                        for m in st.session_state.messages[:-1]:  # 最後(今の質問)以外
                                            role_name = "User" if m["role"] == "user" else "Cheyanne"
                                            chat_context += f"{role_name}: {m['content']}\n"
                                    
                                        chat_context += f"\nUser: {prompt_chat}\nCheyanne:"
                                    
                                        try:
                                            response_chat = safe_generate_content(client, model_choice, chat_context)
                                            response_text = response_chat.text
                                            st.markdown(response_text)
                                            st.session_state.messages.append({"role": "assistant", "content": response_text})
                                        except Exception as e:
                                            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                                                st.error("⚠️ APIの利用制限 (429) に達しました。しばらく待ってから再度質問してください。")
                                                st.session_state.messages.pop() # 追加したばかりのユーザーの発言を取り消す
                                            else:
                                                st.error(f"エラーが発生しました: {e}")


                    except Exception as e:
                        st.error(f"Geminiでの処理中にエラーが発生しました: {e}")
                else:
                    st.info("APIキーが設定されていないため、Cheyanneによる分析はスキップされました。")
            
        except Exception as e:
            st.error(f"データの取得中にエラーが発生しました: {e}")

# マクロ環境スナップショット取得用関数
def get_macro_snapshot():
    try:
        # 主要指数の直近トレンドを取得
        indices = {"日経平均": "^N225", "S&P 500": "^GSPC", "USD/JPY": "JPY=X"}
        snapshot = ""
        for name, sym in indices.items():
            t = yf.Ticker(sym)
            h = t.history(period="5d")
            if not h.empty:
                last_price = h['Close'].iloc[-1]
                prev_price = h['Close'].iloc[0]
                change = (last_price - prev_price) / prev_price * 100
                snapshot += f"- {name}: {last_price:,.2f} ({change:+.2f}% 直近5日間)\n"
        return snapshot
    except Exception:
        return "マクロ情報の取得に失敗しました。"

# 経済ニュース取得用ヘルパー関数
def get_economic_context():
    import urllib.request
    import urllib.parse
    import xml.etree.ElementTree as ET
    
    context = ""
    # 日本と米国の経済ニュースを少しずつ取得
    queries = ["日本 経済 ニュース", "US stock market news"]
    for q in queries:
        try:
            encoded_query = urllib.parse.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                root = ET.fromstring(response.read())
                items = root.findall('.//item')
                for item in items[:5]:
                    title = item.find('title').text
                    context += f"- {title}\n"
        except Exception:
            pass
    return context if context else "ニュース取得に失敗しました。最新の一般的な市況に基づいて判断してください。"

with tab_portfolio:
    st.header("💼 ポートフォリオ診断 & AIアドバイザー")
    
    # --- AIポートフォリオ・デザイナー ---
    # --- AIポートフォリオ・デザイナー Pro ---
    with st.expander("🛠️ AIポートフォリオ・デザイナー Pro", expanded=False):
        st.markdown("あなたの予算と好みに合わせて、最新の経済状況とマクロ環境を反映した精緻なポートフォリオを設計・検証します。")
        
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            budget = st.number_input("投資予算 (円/ドル合算目安)", min_value=10000, value=1000000, step=10000)
            term = st.radio("投資期間", ["短期 (数週間〜数ヶ月)", "中長期 (数年〜)"], horizontal=True)
            target_market = st.radio("ターゲット市場", ["ハイブリッド (JP/US)", "日本株メイン", "米国株メイン"], horizontal=True)
        with d_col2:
            style = st.radio("運用スタンス", ["安定志向 (配当・優良株)", "バランス (安定成長)", "成長重視 (グロース・新興)"], horizontal=True, index=1)
            theme = st.selectbox("注力テーマ", ["AIにお任せ", "半導体・ハイテクロジー", "DX・デジタル化", "高配当・増配銘柄", "クリーンエネルギー・ESG", "円安・輸出関連"])
            etf_preferred = st.checkbox("📈 ETFを重視して設計する", value=False, help="個別銘柄ではなく、指数連動ETFを優先的に組み入れます")
            additional_request = st.text_input("追加のリクエスト（例：分散を最大化して）", placeholder="AIへの要望を自由に入力")

        if st.button("✨ プロ仕様のポートフォリオを設計・検証する", use_container_width=True, type="primary"):
            with st.spinner("市場環境を確認し、シミュレーションを実行中..."):
                economic_news = get_economic_context()
                macro_info = get_macro_snapshot()
                
                design_prompt = f"""
あなたは世界最高峰のポートフォリオ・ストラテジスト「Cheyanne」です。
以下の条件と、現在のリアルタイムのマクロ経済状況に基づいて、プレミアムな投資プランを設計してください。

【投資条件】
- 予算: {budget:,}円
- 期間: {term}
- スタンス: {style}
- 注力テーマ: {theme}
- 市場優先順位: {target_market}
- ETFの優先順位: {"ETFを最優先で組み入れる" if etf_preferred else "個別株も含めて柔軟に選択"}
- ユーザーの追加要望: {additional_request}

【最新のマクロ環境】
{macro_info}

【最新の経済ニュース】
{economic_news}

【指示事項】
- 日本株は1株、米国株も1株からの購入を前提に、予算内で最高のパフォーマンスを追求してください。
- 合計金額を予算内に収めつつ、3〜6銘柄に厳選。
- なぜ現在のマクロ環境（指数や為替）を考慮してこれらの銘柄を選んだのか、プロの視点で解説してください。

【出力形式】
JSON配列形式のみで、以下のキーを含むリストを出力してください：
`"code"` (ティッカー, 日本株は 7203.T), `"name"`, `"shares"` (株数), `"price"` (想定価格), `"currency"` ("JPY" または "USD"), `"reason"` (選定理由)
"""
                try:
                    res = safe_generate_content(client, model_choice, design_prompt)
                    st.session_state.designed_portfolio_text = res.text
                except Exception as e:
                    st.error(f"設計中にエラーが発生しました: {e}")

        # 設計結果の表示
        if "designed_portfolio_text" in st.session_state:
            import json, re
            text = st.session_state.designed_portfolio_text
            match = re.search(r'\[.*\]', text, flags=re.DOTALL)
            if match:
                try:
                    recs = json.loads(match.group(0))
                    st.success("🤖 Cheyanne Pro による提案ポートフォリオ")
                    
                    # テーブル表示
                    suggest_df = pd.DataFrame(recs)
                    st.table(suggest_df[['code', 'name', 'shares', 'price', 'currency', 'reason']])
                    
                    total_suggested = sum(r.get('shares',0) * r.get('price',0) for r in recs)
                    st.info(f"推定合計投資額: 約 ¥{total_suggested:,.0f} (為替変動により多少前後します)")

                    # --- プロフェッショナル分析 ---
                    a_col1, a_col2 = st.columns(2)
                    
                    with a_col1:
                        st.markdown("##### 🌍 通貨構成比")
                        res_curr = suggest_df.groupby('currency').size().reset_index(name='counts')
                        fig_curr = go.Figure(data=[go.Pie(labels=res_curr['currency'], values=res_curr['counts'], hole=.4)])
                        fig_curr.update_layout(margin=dict(l=0, r=0, t=20, b=0), height=250)
                        st.plotly_chart(fig_curr, use_container_width=True)

                    with a_col2:
                        st.markdown("##### 📈 過去1年バックテスト")
                        # 簡易的な収益率の取得
                        with st.spinner("過去のパフォーマンスを算出中..."):
                            codes = [r['code'] for r in recs]
                            perf_data = {}
                            try:
                                for c in codes:
                                    th = yf.Ticker(c).history(period="1y")
                                    if not th.empty:
                                        # 累積リターン
                                        perf_data[c] = (th['Close'] / th['Close'].iloc[0] - 1) * 100
                                if perf_data:
                                    perf_df = pd.DataFrame(perf_data).fillna(method='ffill')
                                    # 加重平均リターン（簡易的に均等配分）
                                    combined_return = perf_df.mean(axis=1)
                                    
                                    # ベンチマーク取得 (S&P500)
                                    bm = yf.Ticker("^GSPC").history(period="1y")
                                    bm_return = (bm['Close'] / bm['Close'].iloc[0] - 1) * 100 if not bm.empty else None
                                    
                                    fig_bt = go.Figure()
                                    fig_bt.add_trace(go.Scatter(x=combined_return.index, y=combined_return, mode='lines', name='提案ポートフォリオ'))
                                    if bm_return is not None:
                                        fig_bt.add_trace(go.Scatter(x=bm_return.index, y=bm_return, mode='lines', name='S&P 500', line=dict(dash='dash')))
                                    
                                    fig_bt.update_layout(height=250, margin=dict(l=0, r=0, t=20, b=0), yaxis_title="収益率 (%)")
                                    st.plotly_chart(fig_bt, use_container_width=True)
                            except Exception:
                                st.caption("（データの制約によりシミュレーションをスキップしました）")

                    if st.button("📥 この提案をポートフォリオ診断に反映する"):
                        new_data = []
                        for r in recs:
                            new_data.append({"Ticker": r['code'], "Shares": r['shares'], "Avg Cost": r['price']})
                        st.session_state.my_portfolio = pd.DataFrame(new_data)
                        save_data(st.session_state.my_portfolio, PORTFOLIO_FILE)
                        st.success("提案を診断シートに反映しました。「保有銘柄の編集」を確認し、「診断を開始」を押してください。")
                        st.rerun()
                        
                except Exception as e:
                    st.write(text)
            else:
                st.write(text)

    st.markdown("---")
    st.markdown("### 🔍 保有銘柄の現在の状況を診断")
    st.markdown("現在保有している銘柄を入力して「診断を開始」ボタンを押すと、Cheyanneがポートフォリオのバランスとリスクを分析します。")

    # 1. ポートフォリオ編集セクション
    with st.expander("📝 保有銘柄の編集", expanded=True):
        st.info("※ 編集を終えたら、下の「🚀 診断を開始」を押すと内容が反映されます。")
        edited_df = st.data_editor(
            st.session_state.my_portfolio,
            num_rows="dynamic",
            column_config={
                "Ticker": st.column_config.TextColumn("ティッカー (例: 7203.T, MSFT)", required=True),
                "Shares": st.column_config.NumberColumn("保有数量", min_value=1, step=1, required=True),
                "Avg Cost": st.column_config.NumberColumn("取得単価", min_value=0.01, required=True),
            },
            key="portfolio_editor",
            use_container_width=True
        )

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        # ボタンが押されたときに、初めてedited_dfの内容をsession_stateに反映
        start_diag = st.button("🚀 診断を開始", use_container_width=True, type="primary")
        if start_diag:
            st.session_state.my_portfolio = edited_df
            save_data(st.session_state.my_portfolio, PORTFOLIO_FILE)

    if start_diag:
        with st.spinner("ポートフォリオの最新データを取得中..."):
            results = []
            for _, row in st.session_state.my_portfolio.iterrows():
                ticker_code = str(row['Ticker']).strip().upper()
                if not ticker_code: continue
                
                try:
                    t = yf.Ticker(ticker_code)
                    info = t.info
                    curr_price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
                    sector = info.get('sector', '不明')
                    industry = info.get('industry', '不明')
                    div_yield = info.get('dividendYield', 0) or 0
                    
                    cost_basis = row['Avg Cost'] * row['Shares']
                    market_value = curr_price * row['Shares']
                    gain_loss = market_value - cost_basis
                    gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis != 0 else 0
                    annual_div = market_value * div_yield
                    
                    results.append({
                        "Ticker": ticker_code,
                        "Name": info.get('shortName', ticker_code),
                        "Sector": sector,
                        "Industry": industry,
                        "Shares": row['Shares'],
                        "Avg Cost": row['Avg Cost'],
                        "Current": curr_price,
                        "Market Value": market_value,
                        "Gain/Loss": gain_loss,
                        "G/L %": gain_loss_pct,
                        "Annual Div": annual_div
                    })
                except Exception as e:
                    st.error(f"{ticker_code} のデータ取得に失敗しました: {e}")

            if results:
                st.session_state.portfolio_results = pd.DataFrame(results)
                # 診断レポートのリセット（新しいポートフォリオで再診させるため）
                st.session_state.portfolio_analysis = None
            else:
                st.session_state.portfolio_results = None

    # 診断結果の表示 (セッションステートにデータがある場合)
    if st.session_state.portfolio_results is not None:
        res_df = st.session_state.portfolio_results
        
        # --- A. 概要メトリクス ---
        st.divider()
        st.subheader("📊 ポートフォリオ概要")
        m1, m2, m3, m4 = st.columns(4)
        total_value = res_df['Market Value'].sum()
        total_cost = (res_df['Avg Cost'] * res_df['Shares']).sum()
        total_gl = total_value - total_cost
        total_gl_pct = (total_gl / total_cost * 100) if total_cost != 0 else 0
        total_div = res_df['Annual Div'].sum()
        
        m1.metric("合計評価額", f"¥{total_value:,.0f}" if total_value > 1000 else f"{total_value:,.2f}")
        m2.metric("評価損益計", f"¥{total_gl:,.0f}", f"{total_gl_pct:+.2f}%")
        m3.metric("配当予想(年)", f"¥{total_div:,.0f}")
        m4.metric("保有銘柄数", f"{len(res_df)} 銘柄")

        # --- B. ストレス・テスト (Risk Simulator) ---
        st.divider()
        st.subheader("🛡️ リスク・ストレス・テスト")
        st.markdown("特定の市場急変シナリオが発生した際の、あなたのポートフォリオの耐性をシミュレーションします。")
        
        risk_col1, risk_col2 = st.columns([1, 2])
        with risk_col1:
            scenario = st.selectbox(
                "検証するシナリオを選択:",
                [
                    "急激な円高 (130円以下への突入)",
                    "米金利の再上昇 (粘着インフレと利下げ後退)",
                    "地政学的リスクによる原油・天然ガス高騰",
                    "世界的なAIブームの沈静化 (ハイテク調整)"
                ],
                key="risk_scenario_select"
            )
            run_stress = st.button("🚨 衝撃耐性をシミュレートする", use_container_width=True, type="secondary")
        
        with risk_col2:
            if run_stress:
                with st.spinner(f"「{scenario}」の影響を計算中..."):
                    # 銘柄リストの文字列化
                    pos_info = ""
                    for _, r in res_df.iterrows():
                        pos_info += f"- {r['Ticker']} ({r['Name']}): セクター={r['Sector']}, 比率={r['Market Value']/total_value*100:.1f}%\n"
                    
                    stress_prompt = f"""
あなたは凄腕のリスクマネージャー「Cheyanne」です。
以下の保有ポートフォリオに対し、想定される市場シナリオが発生した場合の【ストレス・テスト結果】を作成してください。

【検証シナリオ】: {scenario}

【現在のポートフォリオ】:
{pos_info}

【指示事項】:
1. **想定騰落率の推計**: このシナリオが発生した場合、ポートフォリオ全体で何％程度の変動が予想されるか、論理的に推計。
2. **個別銘柄の明暗**: 構成銘柄の中で、特にダメージを受ける銘柄と、逆に耐性がある（または追い風になる）銘柄を特定し、理由を解説。
3. **ヘッジ戦略のアドバイス**: このリスクを軽減するために、どのような銘柄や資産を組み入れるべきか具体的に提言。

Markdown形式で、プロフェッショナルかつ冷静な口調でレポートしてください。
"""
                    try:
                        res_stress = safe_generate_content(client, model_choice, stress_prompt)
                        st.warning(f"⚠️ {scenario} のシミュレーション結果")
                        st.markdown(res_stress.text)
                    except Exception as e:
                        st.error(f"シミュレーション中にエラーが発生しました: {e}")
            else:
                st.info("左側のメニューからシナリオを選択して、シミュレーションを実行してください。")

        # --- C. ビジュアル分析 ---
        st.divider()
        v_col1, v_col2 = st.columns(2)
        with v_col1:
            st.write("**セクター配分**")
            sector_dist = res_df.groupby('Sector')['Market Value'].sum().reset_index()
            fig_pie = go.Figure(data=[go.Pie(labels=sector_dist['Sector'], values=sector_dist['Market Value'], hole=.3)])
            fig_pie.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=300)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with v_col2:
            st.write("**銘柄別損益**")
            fig_bar = go.Figure(data=[go.Bar(x=res_df['Ticker'], y=res_df['G/L %'], marker_color=['#2ca02c' if x >= 0 else '#d62728' for x in res_df['G/L %']])])
            fig_bar.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=300, yaxis_title="騰落率 (%)")
            st.plotly_chart(fig_bar, use_container_width=True)

        # --- D. Cheyanne AI診断 ---
        st.divider()
        st.subheader("🤖 Cheyanne AI診断レポート")
        
        if not api_key:
            st.warning("AI診断を利用するにはAPIキーを設定してください。")
        else:
            # すでに診断結果がある場合はボタンを表示せず結果のみ表示（再診ボタンは別途用意可）
            if st.session_state.portfolio_analysis is None:
                if st.button("🤖 Cheyanneによる総合診断レポートを生成", use_container_width=True):
                    portfolio_summary = res_df[['Ticker', 'Name', 'Sector', 'Market Value', 'G/L %']].to_string()
                    prompt = f"""
あなたはプロの資産運用アドバイザー「Cheyanne」です。
ユーザーの以下のポートフォリオ内容を精査し、プロフェッショナルな診断レポートを作成してください。

【ポートフォリオデータ】
{portfolio_summary}

合計評価額: {total_value}
合計損益率: {total_gl_pct:.2f}%
推定年間配当: {total_div}

【指示事項】
1. **全体のバランス評価**: セクターの偏りや、リスクの集中度合いを評価してください。
2. **パフォーマンス分析**: 現在の損益状況から見える課題。
3. **具体的なアドバイス**: ポートフォリオの堅牢性を高めるために、次に追加すべきセクターや、注意すべきリスク。
4. **今後の見通し**: マクロ経済環境を考慮した、このポートフォリオの将来的な展望。

Markdown形式で、親しみやすくも鋭いプロの視点で出力してください。
"""
                    try:
                        with st.spinner("Cheyanneがポートフォリオを分析中..."):
                            res = client.models.generate_content(
                                model=model_choice,
                                contents=prompt
                            )
                            st.session_state.portfolio_analysis = res.text
                            st.rerun()
                    except Exception as e:
                        st.error(f"AI診断中にエラーが発生しました: {e}")
            else:
                # 診断結果の表示
                st.markdown(st.session_state.portfolio_analysis)
                if st.button("🔄 診断レポートを再生成する"):
                    st.session_state.portfolio_analysis = None
                    st.rerun()

