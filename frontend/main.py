"""営業支援エージェント Streamlit フロントエンド.

agent-first-meeting の FastAPI エンドポイント (/api/first-meeting/generate)
を呼び出して SSE をリアルタイム表示する。
"""
import json
import os

import httpx
import streamlit as st

API_URL = os.environ.get(
    "FIRST_MEETING_API_URL",
    "http://127.0.0.1:8000/api/first-meeting/generate",
)


st.set_page_config(
    page_title="営業支援エージェント",
    page_icon="📋",
    layout="wide",
)

st.title("📋 初回面談アポ資料 自動生成")
st.caption(
    "顧客情報を入力すると、AI エージェントが社内事例を検索して "
    "PowerPoint 提案資料を生成します"
)

with st.form("input_form"):
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input(
            "会社名 *", placeholder="株式会社サンプル製作所"
        )
        industry = st.selectbox(
            "業種 *",
            [
                "製造業",
                "小売業",
                "サービス業",
                "IT・ソフトウェア",
                "金融",
                "建設・不動産",
                "医療・介護",
                "その他",
            ],
        )
    with col2:
        scale = st.selectbox(
            "規模 *",
            ["大企業", "中堅企業", "中小企業", "スタートアップ"],
        )
        salesperson = st.text_input("担当営業（任意）", placeholder="ともや")

    known_info = st.text_area(
        "既知の課題感（任意）",
        placeholder=(
            "DX 推進について悩んでいる、ベテラン社員の高齢化で技能継承が課題、"
            "など自由記述"
        ),
        height=120,
    )

    submitted = st.form_submit_button("🚀 資料を生成", type="primary")


if submitted:
    if not company_name:
        st.error("会社名は必須です")
        st.stop()

    request_body = {
        "companyName": company_name,
        "industry": industry,
        "scale": scale,
        "knownInfo": known_info,
        "salesperson": salesperson,
    }

    st.divider()

    accumulated_text = ""
    document_url: str | None = None

    with st.status("エージェントを起動中...", expanded=True) as status:
        try:
            with httpx.stream(
                "POST",
                API_URL,
                json=request_body,
                timeout=240.0,
            ) as response:
                if response.status_code != 200:
                    status.update(
                        label=f"API エラー (status={response.status_code})",
                        state="error",
                    )
                    st.stop()

                current_event: str | None = None
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_raw = line[len("data:"):].strip()
                        try:
                            data = json.loads(data_raw)
                        except json.JSONDecodeError:
                            continue

                        if current_event == "thought":
                            st.write(f"🤔 {data.get('text', '')}")
                        elif current_event == "tool":
                            tool_name = data.get("name", "?")
                            st.write(f"🔧 ツール呼び出し: `{tool_name}`")
                        elif current_event == "tool_result":
                            tool_name = data.get("name", "?")
                            st.write(f"✅ ツール完了: `{tool_name}`")
                        elif current_event == "message":
                            accumulated_text += data.get("text", "")
                        elif current_event == "done":
                            if data.get("status") == "success":
                                document_url = data.get("data", {}).get(
                                    "documentUrl"
                                )
                                status.update(
                                    label="生成完了 ✅", state="complete"
                                )
                            else:
                                err = data.get("error") or {}
                                status.update(label="エラー", state="error")
                                st.error(
                                    f"{err.get('code', 'Unknown')}: "
                                    f"{err.get('message', '')}"
                                )
                                st.stop()
        except httpx.HTTPError as e:
            status.update(label="接続エラー", state="error")
            st.error(f"FastAPI サーバーに接続できません: {e}")
            st.caption(
                "agent-first-meeting の FastAPI サーバーが "
                f"{API_URL} で起動しているか確認してください。"
            )
            st.stop()

    st.divider()
    st.subheader("📋 エージェント レポート")
    st.markdown(accumulated_text)

    if document_url:
        st.divider()
        st.link_button(
            "📥 PowerPoint をダウンロード",
            url=document_url,
            type="primary",
        )
        st.caption("⏱️ ダウンロードリンクは 24 時間有効です")
