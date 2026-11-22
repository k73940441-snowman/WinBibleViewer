import os
import re
import sys
import sqlite3
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from html.parser import HTMLParser

BIBLE_BOOKS = (
    "",
    "창세기", "출애굽기", "레위기", "민수기", "신명기", "여호수아", "사사기", "룻기", "사무엘상", "사무엘하",
    "열왕기상", "열왕기하", "역대상", "역대하", "에스라", "느헤미야", "에스더", "욥기", "시편", "잠언",
    "전도서", "아가", "이사야", "예레미야", "예레미야애가", "에스겔", "다니엘", "호세아", "요엘", "아모스",
    "오바댜", "요나", "미가", "나훔", "하박국", "스바냐", "학개", "스가랴", "말라기",
    "마태복음", "마가복음", "누가복음", "요한복음", "사도행전", "로마서", "고린도전서", "고린도후서", "갈라디아서", "에베소서",
    "빌립보서", "골로새서", "데살로니가전서", "데살로니가후서", "디모데전서", "디모데후서", "디도서", "빌레몬서", "히브리서", "야고보서",
    "베드로전서", "베드로후서", "요한일서", "요한이서", "요한삼서", "유다서", "요한계시록"
)


class RichTextParser(HTMLParser):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.bold = False
        self.color = None

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in ("b", "strong"):
            self.bold = True
        elif t in ("br", "p", "div"):
            self.text_widget.insert(tk.END, "\n")
        elif t == "font":
            for k, v in attrs:
                if k.lower() == "color" and v:
                    self.color = v if v.startswith("#") else f"#{v}"

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ("b", "strong"):
            self.bold = False
        elif t == "font":
            self.color = None

    def handle_data(self, data):
        if not data:
            return
        tags = []
        if self.bold:
            tags.append("bold")
        if self.color and re.match(r"^#[0-9a-fA-F]{6}$", self.color):
            tag_name = f"color_{self.color}"
            self.text_widget.tag_configure(tag_name, foreground=self.color)
            tags.append(tag_name)
        self.text_widget.insert(tk.END, data, tuple(tags))


class BibleDbViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("성경 DB 통합 뷰어 (.bdb / .cdb / .cmp / .hdb / .sdb)")
        self.root.geometry("950x700")
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "icon.png")
        if os.path.exists(icon_path):
            try:
                self.root.iconphoto(False, tk.PhotoImage(file=icon_path))
            except Exception:
                pass

        self.conn = None
        self.mode = "GENERAL"
        self.active_table = ""
        self.text_col = ""
        self.book_numbers = []
        self.chapter_numbers = []
        self.hymn_chapters = []
        self.table_names = []
        self.font_size = 12

        self._build_ui()

    def _build_ui(self):
        top_frame = ttk.Frame(self.root, padding=8)
        top_frame.pack(fill=tk.X)

        ttk.Button(top_frame, text="📂 DB 파일 열기", command=self.open_file).pack(side=tk.LEFT)

        self.lbl_status = ttk.Label(top_frame, text="지원 파일: .bdb, .cdb, .cmp, .hdb, .sdb", font=("맑은 고딕", 10, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=12)

        ttk.Button(top_frame, text="가+", width=4, command=lambda: self.change_font(1)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_frame, text="가-", width=4, command=lambda: self.change_font(-1)).pack(side=tk.RIGHT, padx=2)

        ctrl_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        ctrl_frame.pack(fill=tk.X)

        self.combo_book = ttk.Combobox(ctrl_frame, state="readonly", width=28, font=("맑은 고딕", 10))
        self.combo_book.pack(side=tk.LEFT, padx=(0, 6))
        self.combo_book.bind("<<ComboboxSelected>>", self.on_book_selected)

        self.combo_chapter = ttk.Combobox(ctrl_frame, state="readonly", width=10, font=("맑은 고딕", 10))
        self.combo_chapter.pack(side=tk.LEFT, padx=(0, 6))
        self.combo_chapter.bind("<<ComboboxSelected>>", self.on_chapter_selected)

        ttk.Button(ctrl_frame, text="◀ 이전", width=7, command=lambda: self.move_chapter(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame, text="다음 ▶", width=7, command=lambda: self.move_chapter(1)).pack(side=tk.LEFT, padx=2)

        ttk.Button(ctrl_frame, text="검색", width=7, command=self.perform_search).pack(side=tk.RIGHT)
        self.entry_search = ttk.Entry(ctrl_frame, width=26, font=("맑은 고딕", 10))
        self.entry_search.pack(side=tk.RIGHT, padx=6)
        self.entry_search.bind("<Return>", lambda e: self.perform_search())
        ttk.Label(ctrl_frame, text="검색:").pack(side=tk.RIGHT)

        text_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        text_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_area = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("맑은 고딕", self.font_size),
            yscrollcommand=scrollbar.set,
            padx=14,
            pady=14,
            spacing3=6,
            bg="#FAFAFA",
            fg="#222222"
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text_area.yview)

        self._setup_tags()
        self.text_area.insert(tk.END, "상단의 [📂 DB 파일 열기] 버튼을 눌러 .bdb, .cdb, .cmp, .hdb, .sdb 파일을 선택하세요.")

    def _setup_tags(self):
        self.text_area.tag_configure("title", font=("맑은 고딕", self.font_size + 3, "bold"), foreground="#111111")
        self.text_area.tag_configure("verse_num", font=("맑은 고딕", self.font_size, "bold"), foreground="#1565C0")
        self.text_area.tag_configure("ref_tag", font=("맑은 고딕", self.font_size, "bold"), foreground="#2E7D32")
        self.text_area.tag_configure("bold", font=("맑은 고딕", self.font_size, "bold"))

    def change_font(self, delta):
        self.font_size = max(9, min(26, self.font_size + delta))
        self.text_area.configure(font=("맑은 고딕", self.font_size))
        self._setup_tags()

    def insert_rich_text(self, raw_text):
        if raw_text is None:
            return
        cleaned = re.sub(r"<W[HG]\d+>", "", str(raw_text))
        if "<" in cleaned and ">" in cleaned:
            try:
                parser = RichTextParser(self.text_area)
                parser.feed(cleaned)
            except Exception:
                self.text_area.insert(tk.END, cleaned)
        else:
            self.text_area.insert(tk.END, cleaned)

    def get_book_name(self, num):
        if 1 <= num < len(BIBLE_BOOKS):
            return f"{num}. {BIBLE_BOOKS[num]}"
        return f"{num}권"

    def open_file(self):
        file_path = filedialog.askopenfilename(
            title="성경 DB 파일 선택",
            filetypes=[
                ("성경 DB 파일", "*.bdb *.cdb *.cmp *.hdb *.sdb *.db *.sqlite"),
                ("모든 파일", "*.*")
            ]
        )
        if not file_path:
            return

        file_name = os.path.basename(file_path)
        _, ext = os.path.splitext(file_name)

        try:
            if self.conn:
                self.conn.close()
            self.conn = sqlite3.connect(file_path)
            cur = self.conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [name for (name,) in cur.fetchall()]

            if not tables:
                raise Exception("테이블이 없는 빈 데이터베이스입니다.")

            hymnal_tbl = next((t for t in tables if t.lower() == "hymnal"), None)
            if hymnal_tbl:
                self.mode = "HYMNAL"
                self.active_table = hymnal_tbl
                self.text_col = "htext"
                self.combo_chapter.pack_forget()
                self.load_hymnal_list()
                self.lbl_status.config(text=f"[찬송가({ext})] {file_name}")
                return

            verse_tbl = None
            detected_col = ""
            for tbl in tables:
                cur.execute(f"PRAGMA table_info([{tbl}])")
                cols = [col_row[1].lower() for col_row in cur.fetchall()]
                if "book" in cols and "chapter" in cols:
                    verse_tbl = tbl
                    for candidate in ("btext", "ctext", "text", "content", "comment", "data", "body", "note"):
                        if candidate in cols:
                            detected_col = candidate
                            break
                    if not detected_col:
                        detected_col = cols[-1]
                    break

            if verse_tbl:
                self.mode = "VERSE_BASED"
                self.active_table = verse_tbl
                self.text_col = detected_col
                if not self.combo_chapter.winfo_ismapped():
                    self.combo_chapter.pack(side=tk.LEFT, padx=(0, 6), after=self.combo_book)
                self.load_books()
                self.lbl_status.config(text=f"[성경/주석({ext})] {file_name}")
                return

            self.mode = "GENERAL"
            self.combo_chapter.pack_forget()
            self.load_general_tables(tables)
            self.lbl_status.config(text=f"[사전/데이터({ext})] {file_name} (테이블 {len(tables)}개)")

        except Exception as e:
            messagebox.showerror("파일 열기 오류", f"파일을 열 수 없습니다:\n{e}")

    def load_books(self):
        cur = self.conn.cursor()
        cur.execute(f"SELECT DISTINCT book FROM [{self.active_table}] ORDER BY book ASC")
        self.book_numbers = [b for (b,) in cur.fetchall()]
        display = [self.get_book_name(b) for b in self.book_numbers]
        self.combo_book["values"] = display
        if display:
            self.combo_book.current(0)
            self.on_book_selected()

    def on_book_selected(self, event=None):
        idx = self.combo_book.current()
        if idx < 0:
            return
        if self.mode == "VERSE_BASED":
            book_num = self.book_numbers[idx]
            cur = self.conn.cursor()
            cur.execute(f"SELECT DISTINCT chapter FROM [{self.active_table}] WHERE book = ? ORDER BY chapter ASC", (book_num,))
            self.chapter_numbers = [c for (c,) in cur.fetchall()]
            self.combo_chapter["values"] = [f"{c}장" for c in self.chapter_numbers]
            if self.chapter_numbers:
                self.combo_chapter.current(0)
                self.on_chapter_selected()
        elif self.mode == "HYMNAL":
            self.load_hymn_detail(self.hymn_chapters[idx])
        elif self.mode == "GENERAL":
            self.active_table = self.table_names[idx]
            self.load_general_data(self.active_table)

    def on_chapter_selected(self, event=None):
        b_idx = self.combo_book.current()
        c_idx = self.combo_chapter.current()
        if b_idx < 0 or c_idx < 0:
            return
        book_num = self.book_numbers[b_idx]
        chap_num = self.chapter_numbers[c_idx]

        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM [{self.active_table}] WHERE book = ? AND chapter = ?", (book_num, chap_num))
        cols = [desc[0].lower() for desc in cur.description]
        rows = cur.fetchall()

        verse_idx = next((i for i, c in enumerate(cols) if c in ("verse", "fromverse")), -1)
        to_verse_idx = next((i for i, c in enumerate(cols) if c == "toverse"), -1)
        text_idx = next((i for i, c in enumerate(cols) if c == self.text_col.lower()), len(cols) - 1)

        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, f"{self.get_book_name(book_num)} {chap_num}장\n\n", "title")

        for r in rows:
            if verse_idx >= 0:
                v1 = r[verse_idx]
                v2 = r[to_verse_idx] if to_verse_idx >= 0 else v1
                label = f"[{v1}-{v2}절]\n" if (v2 and v2 > v1) else f"{v1}  "
            else:
                label = "• "
            self.text_area.insert(tk.END, label, "verse_num")
            self.insert_rich_text(r[text_idx])
            self.text_area.insert(tk.END, "\n\n")

        self.text_area.yview_moveto(0)

    def load_hymnal_list(self):
        cur = self.conn.cursor()
        cur.execute(f"SELECT chapter, title FROM [{self.active_table}] ORDER BY chapter ASC")
        rows = cur.fetchall()
        self.hymn_chapters = [ch for (ch, _) in rows]
        self.combo_book["values"] = [f"{ch}장. {title}" for (ch, title) in rows]
        if rows:
            self.combo_book.current(0)
            self.load_hymn_detail(next(iter(self.hymn_chapters)))

    def load_hymn_detail(self, chap_num):
        cur = self.conn.cursor()
        cur.execute(f"SELECT chapter, title, htext FROM [{self.active_table}] WHERE chapter = ?", (chap_num,))
        row = cur.fetchone()
        self.text_area.delete("1.0", tk.END)
        if row:
            ch, title, htext = row
            self.text_area.insert(tk.END, f"🎵 찬송가 {ch}장 - {title}\n\n", "title")
            self.insert_rich_text(htext)
        self.text_area.yview_moveto(0)

    def load_general_tables(self, tables):
        self.table_names = tables
        self.combo_book["values"] = tables
        if tables:
            self.combo_book.current(0)
            self.active_table = next(iter(tables))
            self.load_general_data(self.active_table)

    def load_general_data(self, table_name):
        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM [{table_name}] LIMIT 300")
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, f"📂 테이블: {table_name} (최대 300개 항목)\n\n", "title")

        for idx, r in enumerate(rows, 1):
            self.text_area.insert(tk.END, f"[{idx}]\n", "ref_tag")
            for c_name, val in zip(cols, r):
                if val is not None and str(val).strip():
                    self.text_area.insert(tk.END, f"• {c_name}: ")
                    self.insert_rich_text(val)
                    self.text_area.insert(tk.END, "\n")
            self.text_area.insert(tk.END, "\n────────────────────\n\n")
        self.text_area.yview_moveto(0)

    def move_chapter(self, delta):
        if self.mode == "HYMNAL":
            nxt = self.combo_book.current() + delta
            if 0 <= nxt < len(self.hymn_chapters):
                self.combo_book.current(nxt)
                self.on_book_selected()
        elif self.mode == "VERSE_BASED":
            nxt_c = self.combo_chapter.current() + delta
            if 0 <= nxt_c < len(self.chapter_numbers):
                self.combo_chapter.current(nxt_c)
                self.on_chapter_selected()
            elif delta > 0 and self.combo_book.current() + 1 < len(self.book_numbers):
                self.combo_book.current(self.combo_book.current() + 1)
                self.on_book_selected()
            elif delta < 0 and self.combo_book.current() - 1 >= 0:
                self.combo_book.current(self.combo_book.current() - 1)
                self.on_book_selected()

    def perform_search(self):
        if not self.conn:
            messagebox.showinfo("알림", "먼저 DB 파일을 열어주세요.")
            return
        kw = self.entry_search.get().strip()
        if not kw:
            return

        cur = self.conn.cursor()
        self.text_area.delete("1.0", tk.END)
        count = 0

        if self.mode == "VERSE_BASED":
            cur.execute(
                f"SELECT * FROM [{self.active_table}] WHERE [{self.text_col}] LIKE ? ORDER BY book ASC, chapter ASC LIMIT 200",
                (f"%{kw}%",)
            )
            cols = [desc[0].lower() for desc in cur.description]
            b_idx = next((i for i, c in enumerate(cols) if c == "book"), -1)
            c_idx = next((i for i, c in enumerate(cols) if c == "chapter"), -1)
            v_idx = next((i for i, c in enumerate(cols) if c in ("verse", "fromverse")), -1)
            t_idx = next((i for i, c in enumerate(cols) if c == self.text_col.lower()), len(cols) - 1)

            for r in cur.fetchall():
                count += 1
                b_num = r[b_idx] if b_idx >= 0 else 0
                b_name = BIBLE_BOOKS[b_num] if (1 <= b_num < len(BIBLE_BOOKS)) else f"{b_num}권"
                ch = r[c_idx] if c_idx >= 0 else 0
                vs = r[v_idx] if v_idx >= 0 else 0
                ref = f"[{b_name} {ch}:{vs}]\n" if vs > 0 else f"[{b_name} {ch}장]\n"
                self.text_area.insert(tk.END, ref, "ref_tag")
                self.insert_rich_text(r[t_idx])
                self.text_area.insert(tk.END, "\n\n")

        elif self.mode == "HYMNAL":
            cur.execute(
                f"SELECT chapter, title, htext FROM [{self.active_table}] WHERE chapter LIKE ? OR title LIKE ? OR htext LIKE ? ORDER BY chapter ASC LIMIT 200",
                (f"%{kw}%", f"%{kw}%", f"%{kw}%")
            )
            for (ch, title, htext) in cur.fetchall():
                count += 1
                self.text_area.insert(tk.END, f"[찬송가 {ch}장 - {title}]\n", "ref_tag")
                self.insert_rich_text(htext)
                self.text_area.insert(tk.END, "\n\n────────────────────\n\n")

        else:
            cur.execute(f"PRAGMA table_info([{self.active_table}])")
            all_cols = [col_name for (_, col_name, _, _, _, _) in cur.fetchall()]
            where = " OR ".join([f"[{c}] LIKE ?" for c in all_cols])
            cur.execute(f"SELECT * FROM [{self.active_table}] WHERE {where} LIMIT 200", [f"%{kw}%"] * len(all_cols))
            cols = [desc[0] for desc in cur.description]
            for r in cur.fetchall():
                count += 1
                self.text_area.insert(tk.END, f"[{count}]\n", "ref_tag")
                for c_name, val in zip(cols, r):
                    if val is not None and str(val).strip():
                        self.text_area.insert(tk.END, f"• {c_name}: ")
                        self.insert_rich_text(val)
                        self.text_area.insert(tk.END, "\n")
                self.text_area.insert(tk.END, "\n────────────────────\n\n")

        self.lbl_status.config(text=f"'{kw}' 검색 결과: {count}건" + (" (최대 200건)" if count >= 200 else ""))
        if count == 0:
            self.text_area.insert(tk.END, f"'{kw}'에 대한 검색 결과가 없습니다.")
        self.text_area.yview_moveto(0)


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = BibleDbViewerApp(root)
        root.mainloop()
    except Exception:
        err_root = tk.Tk()
        err_root.withdraw()
        messagebox.showerror("실행 오류", traceback.format_exc())
