import os
import re
import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from html.parser import HTMLParser

BIBLE_BOOKS = [
    "",
    "창세기", "출애굽기", "레위기", "민수기", "신명기", "여호수아", "사사기", "룻기", "사무엘상", "사무엘하",
    "열왕기상", "열왕기하", "역대상", "역대하", "에스라", "느헤미야", "에스더", "욥기", "시편", "잠언",
    "전도서", "아가", "이사야", "예레미야", "예레미야애가", "에스겔", "다니엘", "호세아", "요엘", "아모스",
    "오바댜", "요나", "미가", "나훔", "하박국", "스바냐", "학개", "스가랴", "말라기",
    "마태복음", "마가복음", "누가복음", "요한복음", "사도행전", "로마서", "고린도전서", "고린도후서", "갈라디아서", "에베소서",
    "빌립보서", "골로새서", "데살로니가전서", "데살로니가후서", "디모데전서", "디모데후서", "디도서", "빌레몬서", "히브리서", "야고보서",
    "베드로전서", "베드로후서", "요한일서", "요한이서", "요한삼서", "유다서", "요한계시록"
]


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

        self.conn = None
        self.mode = "GENERAL"  # VERSE_BASED, HYMNAL, GENERAL
        self.active_table = ""
        self.text_col = ""
        self.book_numbers = []
        self.chapter_numbers = []
        self.hymn_chapters = []
        self.table_names = []
        self.font_size = 12

        self._build_ui()

    def _build_ui(self):
        # 상단 툴바
        top_frame = ttk.Frame(self.root, padding=8)
        top_frame.pack(fill=tk.X)

        ttk.Button(top_frame, text="📂 DB 파일 열기", command=self.open_file).pack(side=tk.LEFT)

        self.lbl_status = ttk.Label(top_frame, text="지원 파일: .bdb, .cdb, .cmp, .hdb, .sdb", font=("맑은 고딕", 10, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=12)

        # 글자 크기 조절
        ttk.Button(top_frame, text="가+", width=4, command=lambda: self.change_font(1)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_frame, text="가-", width=4, command=lambda: self.change_font(-1)).pack(side=tk.RIGHT, padx=2)

        # 선택 및 검색 바
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

        # 검색 영역
        ttk.Button(ctrl_frame, text="검색", width=7, command=self.perform_search).pack(side=tk.RIGHT)
        self.entry_search = ttk.Entry(ctrl_frame, width=26, font=("맑은 고딕", 10))
        self.entry_search.pack(side=tk.RIGHT, padx=6)
        self.entry_search.bind("<Return>", lambda e: self.perform_search())
        ttk.Label(ctrl_frame, text="검색:").pack(side=tk.RIGHT)

        # 본문 출력 영역
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
        if not raw_text:
            return
        cleaned = re.sub(r"<W[HG]\d+>", "", str(raw_text))
        if "<" in cleaned and ">" in cleaned:
            parser = RichTextParser(self.text_area)
            parser.feed(cleaned)
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
        ext = os.path.splitext(file_name)[1].lower()

        try:
            if self.conn:
                self.conn.close()
            self.conn = sqlite3.connect(file_path)
            cur = self.conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cur.fetchall()]

            if not tables:
                raise Exception("테이블이 없는 빈 데이터베이스입니다.")

            # 1. 찬송가 (hymnal)
            hymnal_tbl = next((t for t in tables if t.lower() == "hymnal"), None)
            if hymnal_tbl:
                self.mode = "HYMNAL"
                self.active_table = hymnal_tbl
                self.text_col = "htext"
                self.combo_chapter.pack_forget()
                self.load_hymnal_list()
                self.lbl_status.config(text=f"[찬송가({ext})] {file_name}")
                return

            # 2. 권/장 기반 (성경 .bdb, 주석 .cdb, 비교 .cmp)
            verse_tbl = None
            detected_col = ""
            for tbl in tables:
                cur.execute(f"PRAGMA table_info([{tbl}])")
                cols = [r[1].lower() for r in cur.fetchall()]
                if "book" in cols and "chapter" in cols:
                    verse_tbl = tbl
                    for candidate in ["btext", "ctext", "text", "content", "comment", "data", "body", "note"]:
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

            # 3. 사전(.sdb) 및 일반 테이블
            self.mode = "GENERAL"
            self.combo_chapter.pack_forget()
            self.load_general_tables(tables)
            self.lbl_status.config(text=f"[사전/데이터({ext})] {file_name} (테이블 {len(tables)}개)")

        except Exception as e:
            with open(file_path, "rb") as f:
                header = f.read(32)
            ascii_hdr = "".join(chr(b) if 32 <= b <= 126 else "." for b in header)
            hex_hdr = " ".join(f"{b:02X}" for b in header)
            messagebox.showerror(
                "파일 열기 오류",
                f"이 파일은 표준 비암호화 SQLite3 형식이 아닙니다.\n\n오류: {e}\n\n[파일 헤더 진단]\nASCII: {ascii_hdr}\nHEX: {hex_hdr}"
            )

    def load_books(self):
        cur = self.conn.cursor()
        cur.execute(f"SELECT DISTINCT book FROM [{self.active_table}] ORDER BY book ASC")
        self.book_numbers = [r[0] for r in cur.fetchall()]
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
