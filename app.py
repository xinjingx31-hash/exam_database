import io
import html
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="入試問題データベース", layout="wide")
st.title("入試問題データベース")
st.caption("問題の閲覧は公開されています。登録・編集・PDF作成は招待された編集者のみ利用できます。")

FIELDS = [
    ("university", "大学"), ("faculty", "学部"), ("exam_year", "年度"),
    ("subject", "科目"), ("question_number", "問題番号"), ("field", "分野"),
    ("topic", "単元・テーマ"), ("difficulty", "難易度（1〜10）"),
    ("question_text", "問題文"), ("answer_text", "解答"),
    ("required_knowledge", "解答に必要な知識"), ("advanced_notes", "発展的な内容"),
    ("related_problems", "類題一覧"), ("key_idea", "着眼点"),
    ("method", "解法タグ"), ("solution_summary", "解答の要約"),
    ("teaching_notes", "採点・指導メモ"), ("source_url", "出典URL"),
]

if "access_token" not in st.session_state:
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.editor_email = None

try:
    url = st.secrets["SUPABASE_URL"]
    anon_key = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
except Exception:
    st.error("Supabase接続情報が未設定です。.streamlit/secrets.toml を設定してください。")
    st.stop()

client = create_client(url, anon_key)
if st.session_state.access_token and st.session_state.refresh_token:
    try:
        client.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
    except Exception:
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.editor_email = None

with st.sidebar:
    st.header("編集者ログイン")
    if st.session_state.access_token:
        st.success(f"ログイン中: {st.session_state.editor_email or '編集者'}")
        if st.button("ログアウト"):
            client.auth.sign_out()
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            st.session_state.editor_email = None
            st.rerun()
    else:
        with st.form("login_form"):
            email = st.text_input("招待されたメールアドレス")
            password = st.text_input("パスワード", type="password")
            login = st.form_submit_button("ログイン")
        if login:
            try:
                result = client.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.access_token = result.session.access_token
                st.session_state.refresh_token = result.session.refresh_token
                st.session_state.editor_email = result.user.email
                st.rerun()
            except Exception:
                st.error("ログインできませんでした。メールアドレスとパスワードを確認してください。")

is_editor = bool(st.session_state.access_token)

try:
    result = client.table("problems").select("*").order("id", desc=True).execute()
    problems = result.data or []
except Exception as error:
    st.error(f"データを読み込めません: {error}")
    st.stop()

st.subheader("問題を検索")
search_col, subject_col, year_col, difficulty_col = st.columns([2, 1, 1, 1])
keyword = search_col.text_input("キーワード", placeholder="大学・科目・問題文など")
subjects = sorted({p.get("subject") for p in problems if p.get("subject")})
subject_choice = subject_col.selectbox("科目", ["すべて"] + subjects)
years = sorted({p.get("exam_year") for p in problems if p.get("exam_year")}, reverse=True)
year_choice = year_col.selectbox("年度", ["すべて"] + years)
difficulty_choice = difficulty_col.selectbox("難易度", ["すべて"] + list(range(1, 11)))

filtered = []
for p in problems:
    searchable = " ".join(str(p.get(k) or "") for k in ["university", "faculty", "subject", "question_number", "field", "topic", "question_text", "answer_text", "required_knowledge", "advanced_notes", "related_problems"])
    if keyword and keyword.casefold() not in searchable.casefold():
        continue
    if subject_choice != "すべて" and p.get("subject") != subject_choice:
        continue
    if year_choice != "すべて" and p.get("exam_year") != year_choice:
        continue
    if difficulty_choice != "すべて" and p.get("difficulty") != difficulty_choice:
        continue
    filtered.append(p)

st.caption(f"{len(filtered)} 件")
labels = {
    p["id"]: f"{p.get('university','')} / {p.get('exam_year') or '年度なし'} / {p.get('subject','')} / {p.get('question_number') or '番号なし'}"
    for p in filtered
}
if filtered:
    chosen_id = st.selectbox("詳細を見る問題", list(labels), format_func=lambda pid: labels[pid])
    selected = next(p for p in filtered if p["id"] == chosen_id)
    for key, label in FIELDS:
        value = selected.get(key)
        if value not in (None, ""):
            st.markdown(f"**{label}**")
            if key in ("question_text", "answer_text"):
                st.markdown(str(value))
            else:
                st.write(value)
    try:
        image_rows = client.table("problem_images").select("file_path").eq("problem_id", chosen_id).execute().data or []
        for row in image_rows:
            image_url = client.storage.from_("problem-images").get_public_url(row["file_path"])
            st.image(image_url, use_container_width=True)
    except Exception:
        pass
else:
    st.info("条件に合う問題はありません。")

if is_editor:
    st.divider()
    st.subheader("問題の登録・編集")
    mode = st.radio("操作", ["新しい問題を登録", "選択した問題を編集"], horizontal=True)
    if mode == "新しい問題を登録":
        base = {}
    elif filtered:
        edit_id = st.selectbox("編集する問題", list(labels), format_func=lambda pid: labels[pid], key="edit_id")
        base = next(p for p in problems if p["id"] == edit_id)
    else:
        st.info("編集できる問題がありません。")
        base = None

    if base is not None:
        with st.form("problem_form"):
            values = {}
            cols = st.columns(3)
            for index, (key, label) in enumerate(FIELDS[:8]):
                with cols[index % 3]:
                    if key == "difficulty":
                        options = [""] + list(range(1, 11))
                        old = base.get(key) or ""
                        values[key] = st.selectbox(label, options, index=options.index(old) if old in options else 0)
                    elif key == "exam_year":
                        raw = base.get(key)
                        values[key] = st.text_input(label, value=str(raw) if raw else "")
                    else:
                        values[key] = st.text_input(label, value=str(base.get(key) or ""))
            for key, label in FIELDS[8:]:
                values[key] = st.text_area(label, value=str(base.get(key) or ""), height=100 if key in ("question_text", "answer_text") else 70)
            uploaded = st.file_uploader("添付画像（PNG・GIF）", type=["png", "gif"], accept_multiple_files=True)
            save = st.form_submit_button("保存")
        if save:
            if not values["university"].strip() or not values["subject"].strip():
                st.error("大学と科目は必須です。")
            else:
                try:
                    values["exam_year"] = int(values["exam_year"]) if values["exam_year"].strip() else None
                    if values["exam_year"] is not None and not 1900 <= values["exam_year"] <= 2200:
                        raise ValueError
                except ValueError:
                    st.error("年度は西暦で入力してください。")
                    st.stop()
                payload = {k: (None if v == "" else v) for k, v in values.items()}
                try:
                    if mode == "新しい問題を登録":
                        saved = client.table("problems").insert(payload).execute().data[0]
                        saved_id = saved["id"]
                    else:
                        client.table("problems").update(payload).eq("id", base["id"]).execute()
                        saved_id = base["id"]
                    for file in uploaded or []:
                        image_path = f"{saved_id}/{uuid.uuid4().hex}_{file.name}"
                        client.storage.from_("problem-images").upload(image_path, file.getvalue(), {"upsert": "true", "content-type": file.type})
                        client.table("problem_images").insert({"problem_id": saved_id, "file_path": image_path}).execute()
                    st.success("保存しました。")
                    st.rerun()
                except Exception as error:
                    st.error(f"保存できませんでした: {error}")

st.divider()
st.subheader("問題PDF・解答PDF")
if not is_editor:
    st.info("PDFの作成は招待された編集者のみ利用できます。")
elif filtered:
    pdf_ids = st.multiselect("PDFに含める問題", list(labels), format_func=lambda pid: labels[pid])
    pdf_type = st.radio("PDFの種類", ["問題（解答欄付き）", "解答"], horizontal=True)
    if pdf_ids:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
            from xml.sax.saxutils import escape

            pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle("JapaneseTitle", parent=styles["Title"], fontName="HeiseiMin-W3", alignment=TA_CENTER, fontSize=18)
            head_style = ParagraphStyle("JapaneseHead", parent=styles["Heading2"], fontName="HeiseiMin-W3", fontSize=13)
            body_style = ParagraphStyle("JapaneseBody", parent=styles["BodyText"], fontName="HeiseiMin-W3", fontSize=10, leading=16, wordWrap="CJK")
            def para(text, style=body_style):
                return Paragraph(escape(str(text or "")).replace("\n", "<br/>") or " ", style)
            story = [Paragraph("入試問題" if pdf_type.startswith("問題") else "入試問題 解答", title_style), Spacer(1, 8)]
            for i, pid in enumerate(pdf_ids):
                p = next(x for x in problems if x["id"] == pid)
                story.append(Paragraph(escape(f"{i+1}. {labels[pid]}"), head_style))
                story.extend([Paragraph("問題", body_style), para(p.get("question_text"))])
                if pdf_type.startswith("問題"):
                    story.append(Paragraph("解答欄", body_style))
                    lines = Table([[""]] * 8, colWidths=[170*mm], rowHeights=[18*mm]*8)
                    lines.setStyle(TableStyle([("LINEBELOW", (0,0), (-1,-1), 0.4, colors.grey)]))
                    story.append(lines)
                else:
                    for k, label in [("answer_text","解答"),("solution_summary","解答の要約"),("required_knowledge","必要な知識"),("advanced_notes","発展的な内容")]:
                        if p.get(k):
                            story.extend([Paragraph(label, body_style), para(p[k])])
                if i < len(pdf_ids)-1:
                    story.append(PageBreak())
            buffer = io.BytesIO()
            SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=18*mm, bottomMargin=18*mm).build(story)
            st.download_button("PDFをダウンロード", buffer.getvalue(), "exam_questions.pdf", "application/pdf")
        except ImportError:
            st.error("PDF出力には reportlab が必要です。requirements.txt から自動導入されます。")


