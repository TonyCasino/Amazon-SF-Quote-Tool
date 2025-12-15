import os
import json
import tkinter as tk
from tkinter import ttk, messagebox

from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
from simple_salesforce.exceptions import SalesforceMalformedRequest

# ---------------- GLOBALS ----------------
sf = None  # Salesforce connection
CREDS_FILE = "sf_creds.json"

# Always use this parent Opportunity for child opp list
MASTER_PARENT_OPP_ID = "0064W00001JdubyQAB"

# CPQ / Opportunity field constants
QUOTE_OPPORTUNITY_FIELD = "SBQQ__Opportunity2__c"
PARENT_OPP_FIELD = "Parent_Opportunity__c"

FIELDS_TO_COPY = [
    "SBQQ__Product__c",
    "SBQQ__ListPrice__c",
    "SBQQ__RegularPrice__c",
    "SBQQ__NetPrice__c",
    "SBQQ__Discount__c",
    "SBQQ__SubscriptionPricing__c",
    "SBQQ__Description__c",
    "SAP_Configuration__c",
]


# ---------------- CREDS STORAGE ----------------

def load_saved_creds():
    if not os.path.exists(CREDS_FILE):
        return None
    try:
        with open(CREDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_creds(creds: dict):
    with open(CREDS_FILE, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)


def connect_salesforce_from_creds(creds: dict):
    """
    creds: {"username": ..., "password": ..., "token": ..., "env": "Production"/"Sandbox"}
    """
    domain = "login" if creds.get("env") == "Production" else "test"
    return Salesforce(
        username=creds["username"],
        password=creds["password"],
        security_token=creds["token"],
        domain=domain,
    )


# ---------------- SALESFORCE HELPERS ----------------

def get_quote_by_name(quote_name: str):
    safe_name = quote_name.replace("'", "\\'")
    soql = (
        "SELECT Id, Name, {opp_field} "
        "FROM SBQQ__Quote__c "
        "WHERE Name = '{name}' "
        "ORDER BY CreatedDate DESC LIMIT 1"
    ).format(opp_field=QUOTE_OPPORTUNITY_FIELD, name=safe_name)

    result = sf.query_all(soql)
    recs = result.get("records", [])
    return recs[0] if recs else None


def get_opportunity(opp_id: str):
    soql = f"SELECT Id, Name FROM Opportunity WHERE Id = '{opp_id}' LIMIT 1"
    return sf.query_all(soql).get("records", [None])[0]


def get_child_opportunities(parent_opp_id: str):
    # fetched fields not displayed
    soql = (
        "SELECT Id, Name, StageName, Amount, CloseDate "
        "FROM Opportunity "
        f"WHERE {PARENT_OPP_FIELD} = '{parent_opp_id}' "
        "ORDER BY CreatedDate ASC"
    )
    return sf.query_all(soql).get("records", [])


def get_quote_for_opportunity(opp_id: str):
    soql = (
        "SELECT Id, Name, SBQQ__Primary__c, CreatedDate "
        "FROM SBQQ__Quote__c "
        f"WHERE {QUOTE_OPPORTUNITY_FIELD} = '{opp_id}' "
        "ORDER BY SBQQ__Primary__c DESC, CreatedDate DESC"
    )
    return sf.query_all(soql).get("records", [None])[0]


def get_quote_lines(quote_id: str):
    soql = (
        "SELECT Id, Name, SBQQ__Quantity__c, "
        + ", ".join(FIELDS_TO_COPY) +
        f" FROM SBQQ__QuoteLine__c WHERE SBQQ__Quote__c = '{quote_id}'"
    )
    return sf.query_all(soql).get("records", [])


def copy_lines_with_multiplier(source_lines, target_quote_id: str, multiplier: float):
    created_ids = []

    for line in source_lines:
        new_line = {"SBQQ__Quote__c": target_quote_id}

        # Quantity
        src_qty = line.get("SBQQ__Quantity__c") or 1
        try:
            new_qty = float(src_qty) * float(multiplier)
        except Exception:
            new_qty = float(multiplier)
        new_line["SBQQ__Quantity__c"] = new_qty

        # Other fields
        for field in FIELDS_TO_COPY:
            if field not in line:
                continue
            val = line[field]
            if val is None:
                continue

            if field == "SAP_Configuration__c" and isinstance(val, str):
                val = val[:130000]

            new_line[field] = val

        try:
            result = sf.SBQQ__QuoteLine__c.create(new_line)
            created_ids.append(result.get("id"))
        except SalesforceMalformedRequest as e:
            print("SalesforceMalformedRequest:", e.content)
        except Exception as e:
            print("Error creating quote line:", e)

    return created_ids


# ---------------- SETTINGS WINDOW ----------------

class SettingsWindow(tk.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.title("Salesforce Settings")
        self.resizable(False, False)

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Environment:").grid(row=0, column=0, sticky="e", pady=(0, 6))
        ttk.Label(frm, text="Username:").grid(row=1, column=0, sticky="e", pady=2)
        ttk.Label(frm, text="Password:").grid(row=2, column=0, sticky="e", pady=2)
        ttk.Label(frm, text="Security Token:").grid(row=3, column=0, sticky="e", pady=2)

        self.env_var = tk.StringVar(value="Production")
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.token_var = tk.StringVar()

        saved = load_saved_creds()
        if saved:
            self.env_var.set(saved.get("env", "Production"))
            self.username_var.set(saved.get("username", ""))

        env_combo = ttk.Combobox(
            frm,
            textvariable=self.env_var,
            values=["Production", "Sandbox"],
            state="readonly",
            width=18,
        )
        env_combo.grid(row=0, column=1, sticky="w", pady=(0, 6))

        self.username_entry = ttk.Entry(frm, width=36, textvariable=self.username_var)
        self.password_entry = ttk.Entry(frm, width=36, textvariable=self.password_var, show="*")
        self.token_entry = ttk.Entry(frm, width=36, textvariable=self.token_var)

        self.username_entry.grid(row=1, column=1, sticky="w", pady=2)
        self.password_entry.grid(row=2, column=1, sticky="w", pady=2)
        self.token_entry.grid(row=3, column=1, sticky="w", pady=2)

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=4, column=0, columnspan=2, pady=(12, 0), sticky="e")

        ttk.Button(btn_row, text="Save & Connect", command=self.save_and_connect).pack(side="right")

    def save_and_connect(self):
        global sf

        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        token = self.token_var.get().strip()
        env = self.env_var.get()

        if not username or not password or not token:
            messagebox.showerror("Missing Info", "Please enter username, password, and token.")
            return

        creds = {"username": username, "password": password, "token": token, "env": env}

        try:
            sf = connect_salesforce_from_creds(creds)
        except SalesforceAuthenticationFailed as e:
            msg = getattr(e, "content", None)
            messagebox.showerror("Login Failed", f"SalesforceAuthenticationFailed:\n{msg}")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect:\n{e}")
            return

        save_creds(creds)
        self.parent_app.set_connection_status(username, env)
        messagebox.showinfo("Connected", f"Connected to Salesforce ({env}) as {username}.")
        self.destroy()


# ---------------- PROGRESS POPUP ----------------

class ProgressPopup(tk.Toplevel):
    def __init__(self, parent, title="Working..."):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cancelled = False

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        self.label_title = ttk.Label(frm, text="Working…", font=("Segoe UI", 11, "bold"))
        self.label_title.pack(anchor="w")

        self.label_detail = ttk.Label(frm, text="Starting…", wraplength=520)
        self.label_detail.pack(anchor="w", pady=(6, 0))

        self.label_count = ttk.Label(frm, text="", foreground="#555555")
        self.label_count.pack(anchor="w", pady=(6, 0))

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill="x", pady=(12, 0))

        self.btn_cancel = ttk.Button(btn_row, text="Cancel", command=self.cancel)
        self.btn_cancel.pack(side="right")

        # Keep on top of parent
        self.transient(parent)
        self.grab_set()

        # Center roughly over parent
        self.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")
        except Exception:
            pass

    def _on_close(self):
        # treat closing as cancel
        self.cancel()

    def cancel(self):
        self.cancelled = True
        self.label_detail.config(text="Cancelling after current item…")
        self.btn_cancel.config(state="disabled")
        self.update_idletasks()

    def update_status(self, title=None, detail=None, count_text=None):
        if title is not None:
            self.label_title.config(text=title)
        if detail is not None:
            self.label_detail.config(text=detail)
        if count_text is not None:
            self.label_count.config(text=count_text)
        self.update_idletasks()


# ---------------- MAIN GUI APP ----------------

class QuoteMergerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quote Merger")
        self.root.minsize(980, 640)

        self.target_quote_id = None
        self.target_quote_name = None
        self.parent_opp = None

        self.child_rows = []  # list of dicts: {opp, check_var, qty_entry, widgets[]}

        self.build_ui()
        self.try_auto_login()

    # ---------- UI polish ----------

    def _apply_theme(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("App.TFrame", background="#f3f4f6")
        style.configure("Card.TFrame", background="#ffffff")

        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Muted.TLabel", foreground="#555555")
        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"))

        style.configure("Primary.TButton", padding=(12, 6))
        style.configure("Secondary.TButton", padding=(10, 6))
        style.configure("TEntry", padding=4)

    def build_ui(self):
        self._apply_theme()

        app = ttk.Frame(self.root, style="App.TFrame", padding=14)
        app.pack(fill="both", expand=True)

        # Top card
        top = ttk.Frame(app, style="Card.TFrame", padding=14)
        top.pack(fill="x")

        title_row = ttk.Frame(top, style="Card.TFrame")
        title_row.pack(fill="x")

        ttk.Label(title_row, text="Quote Merger", style="Title.TLabel").pack(side="left")
        ttk.Button(title_row, text="Settings", style="Secondary.TButton", command=self.open_settings).pack(side="right")

        ttk.Separator(top).pack(fill="x", pady=10)

        controls = ttk.Frame(top, style="Card.TFrame")
        controls.pack(fill="x")

        ttk.Label(controls, text="Target Quote Name:", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        self.target_quote_entry = ttk.Entry(controls)
        self.target_quote_entry.grid(row=0, column=1, padx=10, sticky="ew")

        ttk.Button(
            controls,
            text="Load Child Opportunities",
            style="Primary.TButton",
            command=self.load_child_opps
        ).grid(row=0, column=2, padx=(0, 8))

        controls.columnconfigure(1, weight=1)

        self.connection_label = ttk.Label(top, text="Not connected to Salesforce", style="Muted.TLabel")
        self.connection_label.pack(fill="x", pady=(10, 0))

        self.info_label = ttk.Label(top, text="", style="Muted.TLabel")
        self.info_label.pack(fill="x", pady=(4, 0))

        # Bulk actions card
        bulk = ttk.Frame(app, style="Card.TFrame", padding=12)
        bulk.pack(fill="x", pady=12)

        ttk.Label(bulk, text="Bulk actions", style="Header.TLabel").pack(anchor="w")

        bulk_row = ttk.Frame(bulk, style="Card.TFrame")
        bulk_row.pack(fill="x", pady=(8, 0))

        ttk.Button(bulk_row, text="Check All", style="Secondary.TButton", command=self.check_all).pack(side="left")
        ttk.Button(bulk_row, text="Uncheck All", style="Secondary.TButton", command=self.uncheck_all).pack(side="left", padx=6)

        ttk.Label(bulk_row, text="Set qty for checked:", style="Header.TLabel").pack(side="left", padx=(16, 6))
        self.bulk_qty_var = tk.StringVar(value="1")
        self.bulk_qty_entry = ttk.Entry(bulk_row, textvariable=self.bulk_qty_var, width=10, justify="center")
        self.bulk_qty_entry.pack(side="left")
        ttk.Button(bulk_row, text="Apply", style="Secondary.TButton", command=self.apply_bulk_qty).pack(side="left", padx=6)

        # Table card
        table_card = ttk.Frame(app, style="Card.TFrame", padding=12)
        table_card.pack(fill="both", expand=True)

        header_frame = ttk.Frame(table_card, style="Card.TFrame")
        header_frame.pack(fill="x", pady=(0, 6))

        ttk.Label(header_frame, text="Select", style="Header.TLabel", width=8).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(header_frame, text="Child Opportunity", style="Header.TLabel", width=70).grid(row=0, column=1, sticky="w")
        ttk.Label(header_frame, text="Qty", style="Header.TLabel", width=10).grid(row=0, column=2, sticky="w", padx=(8, 0))

        body = ttk.Frame(table_card, style="Card.TFrame")
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(body, highlightthickness=0, bg="#ffffff")
        self.canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")

        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.rows_inner = ttk.Frame(self.canvas, style="Card.TFrame")
        self.canvas.create_window((0, 0), window=self.rows_inner, anchor="nw")

        # mousewheel (Windows)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Bottom action bar
        bottom = ttk.Frame(app, style="Card.TFrame", padding=12)
        bottom.pack(fill="x", pady=(12, 0))

        ttk.Label(bottom, text="When you click Copy, a progress window will show what it's doing.", style="Muted.TLabel").pack(side="left")

        ttk.Button(
            bottom,
            text="Copy Checked to Target Quote",
            style="Primary.TButton",
            command=self.copy_checked
        ).pack(side="right")

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    # ---------- Salesforce connection ----------

    def set_connection_status(self, username: str, env: str):
        self.connection_label.config(text=f"Connected to Salesforce ({env}) as {username}")

    def try_auto_login(self):
        global sf
        creds = load_saved_creds()
        if not creds:
            self.connection_label.config(text="Not connected to Salesforce (click Settings to configure)")
            return
        try:
            sf = connect_salesforce_from_creds(creds)
            self.set_connection_status(creds.get("username", "unknown"), creds.get("env", "Production"))
        except Exception as e:
            self.connection_label.config(text=f"Failed to auto-connect: {e}. Click Settings to configure.")
            sf = None

    def open_settings(self):
        SettingsWindow(self)

    def ensure_connected(self):
        if sf is None:
            messagebox.showerror("Not Connected", "Please configure Salesforce credentials (Settings) first.")
            return False
        return True

    # ---------- Row management ----------

    def clear_rows(self):
        for row in self.child_rows:
            for widget in row["widgets"]:
                try:
                    widget.destroy()
                except Exception:
                    pass
        self.child_rows = []

    def check_all(self):
        for r in self.child_rows:
            r["check_var"].set(1)

    def uncheck_all(self):
        for r in self.child_rows:
            r["check_var"].set(0)

    def _parse_qty(self, qty_str: str):
        s = (qty_str or "").strip()
        if not s:
            return 1.0
        try:
            return float(s)
        except Exception:
            return None

    def apply_bulk_qty(self):
        qty = self._parse_qty(self.bulk_qty_var.get())
        if qty is None:
            messagebox.showerror("Invalid Qty", "Qty must be a number (e.g., 1, 2, 0.5).")
            return

        any_checked = any(r["check_var"].get() == 1 for r in self.child_rows)
        if not any_checked:
            messagebox.showinfo("None Checked", "Check at least one row first.")
            return

        for r in self.child_rows:
            if r["check_var"].get() == 1:
                r["qty_entry"].delete(0, "end")
                r["qty_entry"].insert(0, str(qty))

    # ---------- Actions ----------

    def load_child_opps(self):
        if not self.ensure_connected():
            return

        qname = self.target_quote_entry.get().strip()
        if not qname:
            messagebox.showerror("Error", "Enter a target quote name.")
            return

        try:
            quote = get_quote_by_name(qname)
        except Exception as e:
            messagebox.showerror("Error", f"Error querying quote:\n{e}")
            return

        if not quote:
            messagebox.showerror("Not found", f"No quote found with name '{qname}'.")
            return

        self.target_quote_id = quote["Id"]
        self.target_quote_name = quote["Name"]

        parent_opp_id = MASTER_PARENT_OPP_ID

        try:
            self.parent_opp = get_opportunity(parent_opp_id)
            child_opps = get_child_opportunities(parent_opp_id)
        except Exception as e:
            messagebox.showerror("Error", f"Error querying opportunities:\n{e}")
            return

        parent_name = self.parent_opp["Name"] if self.parent_opp else parent_opp_id

        self.info_label.config(
            text=(
                f"Target Quote: {self.target_quote_name} ({self.target_quote_id})\n"
                f"Parent Opp (fixed): {parent_name} ({parent_opp_id})\n"
                f"Child Opps Found: {len(child_opps)}"
            )
        )

        self.clear_rows()

        for i, opp in enumerate(child_opps):
            widgets = []
            check_var = tk.IntVar(value=0)

            # zebra striping background
            row_bg = "#f7f7f8" if i % 2 == 0 else "#ffffff"

            chk = ttk.Checkbutton(self.rows_inner, variable=check_var)
            chk.grid(row=i, column=0, padx=(0, 10), pady=4, sticky="w")
            widgets.append(chk)

            name_lbl = tk.Label(
                self.rows_inner,
                text=opp.get("Name", ""),
                width=70,
                anchor="w",
                bg=row_bg,
                fg="#111111",
                padx=10,
                pady=6
            )
            name_lbl.grid(row=i, column=1, pady=4, sticky="ew")
            widgets.append(name_lbl)

            qty_entry = ttk.Entry(self.rows_inner, width=10, justify="center")
            qty_entry.insert(0, "1")
            qty_entry.grid(row=i, column=2, padx=(10, 0), pady=4, sticky="w")
            widgets.append(qty_entry)

            self.child_rows.append(
                {
                    "opp": opp,
                    "check_var": check_var,
                    "qty_entry": qty_entry,
                    "widgets": widgets,
                }
            )

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def copy_checked(self):
        if not self.ensure_connected():
            return

        if not self.target_quote_id:
            messagebox.showerror("Error", "Load a target quote first.")
            return

        selected = [r for r in self.child_rows if r["check_var"].get() == 1]
        if not selected:
            messagebox.showinfo("None Selected", "Check at least one child opportunity.")
            return

        progress = ProgressPopup(self.root, title="Copying to Target Quote")
        progress.update_status(
            title="Preparing…",
            detail=f"Target quote: {self.target_quote_name}",
            count_text=f"0/{len(selected)} complete"
        )

        total_created = 0
        details = []

        for idx, r in enumerate(selected, start=1):
            if progress.cancelled:
                details.append("Cancelled by user.")
                break

            opp = r["opp"]
            name = opp.get("Name", "(unknown)")
            opp_id = opp.get("Id")

            qty_val = self._parse_qty(r["qty_entry"].get())
            if qty_val is None:
                details.append(f"{name}: invalid qty (must be a number). Skipped.")
                progress.update_status(
                    title="Working…",
                    detail=f"({idx}/{len(selected)}) Skipped (invalid qty): {name}",
                    count_text=f"{idx}/{len(selected)} processed — {total_created} lines created"
                )
                continue

            progress.update_status(
                title="Working…",
                detail=f"({idx}/{len(selected)}) Copying lines from: {name}  (qty x{qty_val})",
                count_text=f"{idx-1}/{len(selected)} complete — {total_created} lines created"
            )

            try:
                quote = get_quote_for_opportunity(opp_id)
            except Exception as e:
                details.append(f"{name}: error fetching quote: {e}")
                continue

            if not quote:
                details.append(f"{name}: no quote found.")
                continue

            try:
                lines = get_quote_lines(quote["Id"])
            except Exception as e:
                details.append(f"{name}: error fetching quote lines: {e}")
                continue

            if not lines:
                details.append(f"{name}: quote {quote['Name']} has no lines.")
                continue

            created = copy_lines_with_multiplier(lines, self.target_quote_id, qty_val)
            total_created += len(created)
            details.append(f"{name}: copied {len(created)} line(s) @ qty x{qty_val}.")

            progress.update_status(
                title="Working…",
                detail=f"({idx}/{len(selected)}) Done: {name}",
                count_text=f"{idx}/{len(selected)} processed — {total_created} lines created"
            )

        try:
            progress.update_status(title="Finished", detail="Done.", count_text=f"{total_created} total lines created")
            progress.grab_release()
            progress.destroy()
        except Exception:
            pass

        messagebox.showinfo(
            "Done",
            f"Created {total_created} new quote line(s) on target quote {self.target_quote_name} "
            f"({self.target_quote_id}).\n\n" + "\n".join(details),
        )


# ---------------- ENTRY POINT ----------------

if __name__ == "__main__":
    root = tk.Tk()
    app = QuoteMergerApp(root)
    root.mainloop()
