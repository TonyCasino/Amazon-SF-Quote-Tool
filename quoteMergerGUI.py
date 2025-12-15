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

        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Environment:").grid(row=0, column=0, sticky="e", pady=(0, 5))
        ttk.Label(frm, text="Username:").grid(row=1, column=0, sticky="e")
        ttk.Label(frm, text="Password:").grid(row=2, column=0, sticky="e")
        ttk.Label(frm, text="Security Token:").grid(row=3, column=0, sticky="e")

        self.env_var = tk.StringVar(value="Production")
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.token_var = tk.StringVar()

        # Prefill from saved creds if present
        saved = load_saved_creds()
        if saved:
            self.env_var.set(saved.get("env", "Production"))
            self.username_var.set(saved.get("username", ""))

        env_combo = ttk.Combobox(
            frm,
            textvariable=self.env_var,
            values=["Production", "Sandbox"],
            state="readonly",
            width=15,
        )
        env_combo.grid(row=0, column=1, sticky="w", pady=(0, 5))

        self.username_entry = ttk.Entry(frm, width=35, textvariable=self.username_var)
        self.password_entry = ttk.Entry(frm, width=35, textvariable=self.password_var, show="*")
        self.token_entry = ttk.Entry(frm, width=35, textvariable=self.token_var)

        self.username_entry.grid(row=1, column=1, sticky="w")
        self.password_entry.grid(row=2, column=1, sticky="w")
        self.token_entry.grid(row=3, column=1, sticky="w")

        ttk.Button(frm, text="Save & Connect", command=self.save_and_connect).grid(
            row=4, column=0, columnspan=2, pady=12
        )

    def save_and_connect(self):
        global sf

        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        token = self.token_var.get().strip()
        env = self.env_var.get()

        if not username or not password or not token:
            messagebox.showerror("Missing Info", "Please enter username, password, and token.")
            return

        creds = {
            "username": username,
            "password": password,
            "token": token,
            "env": env,
        }

        # Try connecting
        try:
            sf = connect_salesforce_from_creds(creds)
        except SalesforceAuthenticationFailed as e:
            msg = getattr(e, "content", None)
            messagebox.showerror("Login Failed", f"SalesforceAuthenticationFailed:\n{msg}")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect:\n{e}")
            return

        # Save creds
        save_creds(creds)

        # Update parent UI
        self.parent_app.set_connection_status(username, env)
        messagebox.showinfo("Connected", f"Connected to Salesforce ({env}) as {username}.")
        self.destroy()

# ---------------- MAIN GUI APP ----------------

class QuoteMergerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quote Merger")

        self.child_rows = []
        self.target_quote_id = None
        self.target_quote_name = None
        self.parent_opp = None

        self.connection_label = None

        self.build_ui()
        self.try_auto_login()

    def build_ui(self):
        # Top bar: quote input + gear
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill="x")

        ttk.Label(top_frame, text="Target Quote Name:").grid(row=0, column=0, sticky="w")
        self.target_quote_entry = ttk.Entry(top_frame, width=40)
        self.target_quote_entry.grid(row=0, column=1, padx=5)

        self.load_button = ttk.Button(top_frame, text="Load Child Opportunities", command=self.load_child_opps)
        self.load_button.grid(row=0, column=2, padx=5)

        # Gear button (settings)
        self.settings_button = ttk.Button(top_frame, text="⚙", width=3, command=self.open_settings)
        self.settings_button.grid(row=0, column=3, padx=5)

        # Connection status
        self.connection_label = ttk.Label(self.root, text="Not connected to Salesforce", padding=(10, 0))
        self.connection_label.pack(fill="x")

        # Info label
        self.info_label = ttk.Label(self.root, text="", padding=(10, 5))
        self.info_label.pack(fill="x")

        # Child opp table
        table_outer = ttk.Frame(self.root, padding=10)
        table_outer.pack(fill="both", expand=True)

        headers = ["Select", "Name", "Id", "Stage", "Amount", "Close Date", "Multiplier"]
        widths = [8, 26, 22, 16, 10, 12, 10]

        header_frame = ttk.Frame(table_outer)
        header_frame.pack(fill="x")

        for i, (h, w) in enumerate(zip(headers, widths)):
            ttk.Label(header_frame, text=h, width=w).grid(row=0, column=i, padx=2, sticky="w")

        self.canvas = tk.Canvas(table_outer, height=260)
        self.canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(table_outer, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")

        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.rows_inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.rows_inner, anchor="nw")

        # Bottom frame: action button
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")

        self.copy_button = ttk.Button(bottom, text="Copy Selected to Target Quote", command=self.copy_selected)
        self.copy_button.pack(side="right")

    def set_connection_status(self, username: str, env: str):
        self.connection_label.config(text=f"Connected to Salesforce ({env}) as {username}")

    def try_auto_login(self):
        """
        On startup, try to load saved creds and connect silently.
        """
        global sf
        creds = load_saved_creds()
        if not creds:
            self.connection_label.config(text="Not connected to Salesforce (click ⚙ to configure)")
            return

        try:
            sf = connect_salesforce_from_creds(creds)
            self.set_connection_status(creds.get("username", "unknown"), creds.get("env", "Production"))
        except Exception as e:
            self.connection_label.config(
                text=f"Failed to auto-connect: {e}. Click ⚙ to configure."
            )
            sf = None

    def open_settings(self):
        SettingsWindow(self)

    def clear_rows(self):
        for row in self.child_rows:
            for widget in row["widgets"]:
                widget.destroy()
        self.child_rows = []

    def ensure_connected(self):
        if sf is None:
            messagebox.showerror("Not Connected", "Please configure Salesforce credentials (⚙) first.")
            return False
        return True

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

        # Always use fixed parent opp for child opp list
        parent_opp_id = MASTER_PARENT_OPP_ID

        try:
            self.parent_opp = get_opportunity(parent_opp_id)
            child_opps = get_child_opportunities(parent_opp_id)
        except Exception as e:
            messagebox.showerror("Error", f"Error querying opportunities:\n{e}")
            return

        parent_name = self.parent_opp["Name"] if self.parent_opp else parent_opp_id

        self.info_label.config(
            text=f"Target Quote: {self.target_quote_name} ({self.target_quote_id})\n"
                 f"Parent Opp (fixed): {parent_name} ({parent_opp_id})\n"
                 f"Child Opps Found: {len(child_opps)}"
        )

        self.clear_rows()

        for i, opp in enumerate(child_opps):
            w = []

            var = tk.IntVar()
            chk = ttk.Checkbutton(self.rows_inner, variable=var)
            chk.grid(row=i, column=0, padx=2)
            w.append(chk)

            lbl_name = ttk.Label(self.rows_inner, text=opp["Name"], width=26)
            lbl_name.grid(row=i, column=1, sticky="w")
            w.append(lbl_name)

            lbl_id = ttk.Label(self.rows_inner, text=opp["Id"], width=22)
            lbl_id.grid(row=i, column=2, sticky="w")
            w.append(lbl_id)

            lbl_stage = ttk.Label(self.rows_inner, text=opp.get("StageName"), width=16)
            lbl_stage.grid(row=i, column=3, sticky="w")
            w.append(lbl_stage)

            lbl_amt = ttk.Label(self.rows_inner, text=str(opp.get("Amount")), width=10)
            lbl_amt.grid(row=i, column=4, sticky="w")
            w.append(lbl_amt)

            lbl_close = ttk.Label(self.rows_inner, text=str(opp.get("CloseDate")), width=12)
            lbl_close.grid(row=i, column=5, sticky="w")
            w.append(lbl_close)

            ent_mult = ttk.Entry(self.rows_inner, width=8)
            ent_mult.insert(0, "1")
            ent_mult.grid(row=i, column=6)
            w.append(ent_mult)

            self.child_rows.append({
                "opp": opp,
                "check": var,
                "mult": ent_mult,
                "widgets": w,
            })

    def copy_selected(self):
        if not self.ensure_connected():
            return

        if not self.target_quote_id:
            messagebox.showerror("Error", "Load a target quote first.")
            return

        selected = [r for r in self.child_rows if r["check"].get() == 1]
        if not selected:
            messagebox.showinfo("None Selected", "Select at least one child opportunity.")
            return

        total = 0
        details = []

        for r in selected:
            opp = r["opp"]
            name = opp["Name"]
            opp_id = opp["Id"]

            try:
                multiplier = float(r["mult"].get())
            except Exception:
                multiplier = 1.0

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

            created = copy_lines_with_multiplier(lines, self.target_quote_id, multiplier)
            total += len(created)
            details.append(f"{name}: copied {len(created)} line(s).")

        messagebox.showinfo(
            "Done",
            f"Created {total} new quote line(s) on target quote {self.target_quote_name} "
            f"({self.target_quote_id}).\n\n" + "\n".join(details),
        )

# ---------------- ENTRY POINT ----------------

if __name__ == "__main__":
    root = tk.Tk()
    app = QuoteMergerApp(root)
    root.mainloop()
