"""営業支援エージェント Streamlit フロントエンド.

agent-first-meeting の FastAPI エンドポイント (/api/first-meeting/generate)
を呼び出して SSE をリアルタイム表示する。
"""
import json
import os
import time

import httpx
import streamlit as st

API_URL = os.environ.get(
    "FIRST_MEETING_API_URL",
    "http://127.0.0.1:8000/api/first-meeting/generate",
)
# 公開時の不正利用対策：共有アクセスコード（未設定なら制限なし＝ローカル/開発）。
# 審査員にはこのコードを提出フォームに記載して共有する。
ACCESS_CODE = os.environ.get("APP_ACCESS_CODE", "")
# 1セッションあたりの連続実行クールダウン秒（コスト暴走の保険）
MIN_INTERVAL_SEC = int(os.environ.get("APP_MIN_INTERVAL_SEC", "15"))


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

# 公開時のアクセスゲート：コードが設定されていれば、一致するまで以降を表示しない。
if ACCESS_CODE and not st.session_state.get("authed"):
    st.info("このデモはアクセスコードで保護されています。配布されたコードを入力してください。")
    code = st.text_input("アクセスコード", type="password")
    if st.button("入室"):
        if code == ACCESS_CODE:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("アクセスコードが正しくありません。")
    st.stop()

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
        homepage_url = st.text_input(
            "企業ホームページ URL（任意）",
            placeholder="https://example.co.jp",
        )
    with col2:
        scale = st.selectbox(
            "規模 *",
            ["大企業", "中堅企業", "中小企業", "スタートアップ"],
        )
        salesperson = st.text_input("担当営業（任意）")
        meeting_status_label = st.selectbox(
            "面談回数ステータス *",
            ["初回", "2回目以降"],
        )

    st.markdown("**取引相手の情報（任意）**")
    col3, col4, col5 = st.columns(3)
    with col3:
        contact_name = st.text_input("氏名", placeholder="山田 太郎")
    with col4:
        contact_department = st.text_input("部署", placeholder="経営企画部")
    with col5:
        contact_position = st.text_input("役職", placeholder="部長")

    known_info = st.text_area(
        "既知の課題感（任意）",
        placeholder=(
            "DX 推進について悩んでいる、ベテラン社員の高齢化で技能継承が課題、"
            "など自由記述"
        ),
        height=120,
    )

    last_meeting_notes = st.text_area(
        "前回面談メモ（「2回目以降」の場合）",
        placeholder=(
            "前回面談で実際に起きたこと（相手の反応・合意事項・宿題など）。"
            "記入すると前回実績として記録され、今回の継続提案の根拠になります。"
            "初回の場合は空欄で構いません。"
        ),
        height=120,
    )

    submitted = st.form_submit_button("🚀 資料を生成", type="primary")


if submitted:
    if not company_name:
        st.error("会社名は必須です")
        st.stop()

    # 連続実行クールダウン（1セッションあたりのコスト暴走を抑える保険）
    _last = st.session_state.get("last_submit_ts", 0.0)
    _wait = MIN_INTERVAL_SEC - (time.time() - _last)
    if _wait > 0:
        st.warning(f"連続実行を防ぐため、あと約 {int(_wait) + 1} 秒お待ちください。")
        st.stop()
    st.session_state["last_submit_ts"] = time.time()

    request_body = {
        "companyName": company_name,
        "industry": industry,
        "scale": scale,
        "knownInfo": known_info,
        "salesperson": salesperson,
        "homepageUrl": homepage_url,
        "contactName": contact_name,
        "contactDepartment": contact_department,
        "contactPosition": contact_position,
        "meetingStatus": "first" if meeting_status_label == "初回" else "followup",
        "lastMeetingNotes": last_meeting_notes,
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
                            status_val = data.get("status")
                            if status_val in ("success", "partial"):
                                payload = data.get("data") or {}
                                document_url = payload.get("documentUrl")
                                warnings = payload.get("warnings") or []
                                if status_val == "partial":
                                    status.update(
                                        label="生成完了（警告あり） ⚠️",
                                        state="complete",
                                    )
                                else:
                                    status.update(
                                        label="生成完了 ✅", state="complete"
                                    )
                                for w in warnings:
                                    st.warning(w)
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
