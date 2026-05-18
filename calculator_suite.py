import csv
import json
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox

import ttkbootstrap as ttk


THEMES = ("cyborg", "vapor", "superhero", "darkly")
APP_TITLE = "NEXUS CALCULATOR SUITE"
APP_AUTHOR = "Samuel Musa"
APP_COPYRIGHT = "(c) 2026 Samuel Musa"
APP_FONT = ("Segoe UI", 11)
RESULT_FONT = ("Cascadia Mono", 11)


def safe_font(preferred, fallback, size=11, weight="normal"):
    families = set(font.families())
    family = preferred if preferred in families else fallback
    return (family, size, weight)


def parse_float(entry, field_name, allow_zero=False):
    value = entry.get().strip()
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid number.") from exc

    if parsed < 0 or (parsed == 0 and not allow_zero):
        label = "zero or greater" if allow_zero else "greater than zero"
        raise ValueError(f"{field_name} must be {label}.")
    return parsed


def parse_int(entry, field_name, allow_zero=False):
    value = entry.get().strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a whole number.") from exc

    if parsed < 0 or (parsed == 0 and not allow_zero):
        label = "zero or greater" if allow_zero else "greater than zero"
        raise ValueError(f"{field_name} must be {label}.")
    return parsed


def money(value, prefix="$"):
    return f"{prefix}{value:,.2f}"


def copy_to_clipboard(widget, text):
    widget.clipboard_clear()
    widget.clipboard_append(text)


class DCABreakevenTab(ttk.Frame):
    display_name = "DCA Breakeven"

    def __init__(self, parent, on_status):
        super().__init__(parent, padding=18)
        self.on_status = on_status
        self.purchases = []
        self.last_result = ""
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        input_frame = ttk.Labelframe(self, text="Purchase Input", padding=14)
        input_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))

        self.price_entry = self._entry(input_frame, "Purchase Price", 0)
        self.amount_entry = self._entry(input_frame, "Amount", 1)
        self.fee_entry = self._entry(input_frame, "Fee %", 2, "0.1")
        self.profit_entry = self._entry(input_frame, "Target Profit %", 3, "5")

        buttons = ttk.Frame(input_frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for col in range(2):
            buttons.columnconfigure(col, weight=1)

        ttk.Button(buttons, text="Add Purchase", command=self.add_purchase, bootstyle="primary").grid(
            row=0, column=0, sticky="ew", padx=(0, 6), pady=4
        )
        ttk.Button(buttons, text="Remove Selected", command=self.remove_selected, bootstyle="secondary").grid(
            row=0, column=1, sticky="ew", padx=(6, 0), pady=4
        )
        ttk.Button(buttons, text="Clear All", command=self.clear_purchases, bootstyle="warning").grid(
            row=1, column=0, sticky="ew", padx=(0, 6), pady=4
        )
        ttk.Button(buttons, text="Calculate BE & TP", command=self.calculate, bootstyle="success").grid(
            row=1, column=1, sticky="ew", padx=(6, 0), pady=4
        )

        result_frame = ttk.Labelframe(self, text="Result HUD", padding=14)
        result_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 14))
        result_frame.columnconfigure(0, weight=1)

        self.be_var = tk.StringVar(value="BE Price: --")
        self.tp_var = tk.StringVar(value="TP Price: --")
        self.meta_var = tk.StringVar(value="Add purchases to activate the breakeven matrix.")

        ttk.Label(result_frame, textvariable=self.be_var, font=RESULT_FONT, bootstyle="info").grid(
            row=0, column=0, sticky="w", pady=5
        )
        ttk.Label(result_frame, textvariable=self.tp_var, font=RESULT_FONT, bootstyle="success").grid(
            row=1, column=0, sticky="w", pady=5
        )
        ttk.Label(result_frame, textvariable=self.meta_var, wraplength=520).grid(row=2, column=0, sticky="w", pady=5)
        ttk.Button(result_frame, text="Copy Result", command=self.copy_result, bootstyle="info-outline").grid(
            row=3, column=0, sticky="e", pady=(10, 0)
        )

        history_frame = ttk.Labelframe(self, text="Purchase History", padding=10)
        history_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)

        columns = ("index", "price", "amount", "fee", "units", "cost")
        self.tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=12)
        headers = {
            "index": "#",
            "price": "Price",
            "amount": "Amount",
            "fee": "Fee %",
            "units": "Units",
            "cost": "Cost incl. fee",
        }
        widths = {"index": 48, "price": 130, "amount": 130, "fee": 90, "units": 150, "cost": 150}
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=widths[col], anchor="e")
        self.tree.column("index", anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(history_frame, orient="vertical", command=self.tree.yview).grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=lambda *args: history_frame.children["!scrollbar"].set(*args))

    def _entry(self, parent, label, row, default=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        entry = ttk.Entry(parent, justify="right", width=20)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        if default:
            entry.insert(0, default)
        return entry

    def primary_action(self):
        self.add_purchase()

    def secondary_action(self):
        self.calculate()

    def add_purchase(self):
        try:
            price = parse_float(self.price_entry, "Purchase price")
            amount = parse_float(self.amount_entry, "Amount")
            fee_percent = parse_float(self.fee_entry, "Fee percentage", allow_zero=True)
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc))
            return

        fee = amount * fee_percent / 100
        effective_amount = amount - fee
        units = effective_amount / price
        self.purchases.append({"price": price, "amount": amount, "fee": fee_percent, "units": units})
        self.price_entry.delete(0, tk.END)
        self.amount_entry.delete(0, tk.END)
        self._refresh_tree()
        self.on_status("Purchase added.")

    def remove_selected(self):
        selected = self.tree.selection()
        if not selected:
            self.on_status("Select a purchase to remove.", "warning")
            return
        indexes = sorted((self.tree.index(item) for item in selected), reverse=True)
        for index in indexes:
            self.purchases.pop(index)
        self._refresh_tree()
        self.on_status("Selected purchase removed.")

    def clear_purchases(self):
        self.purchases.clear()
        self.last_result = ""
        self.be_var.set("BE Price: --")
        self.tp_var.set("TP Price: --")
        self.meta_var.set("Purchase history cleared.")
        self._refresh_tree()
        self.on_status("All purchases cleared.")

    def calculate(self):
        if not self.purchases:
            self.on_status("No purchases entered.", "warning")
            return
        try:
            profit_percent = parse_float(self.profit_entry, "Target profit percentage")
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc))
            return

        total_invested = sum(item["amount"] for item in self.purchases)
        total_units = sum(item["units"] for item in self.purchases)
        be_price = total_invested / total_units if total_units else 0
        tp_price = be_price * (1 + profit_percent / 100)
        percentage_gain = (tp_price - be_price) / be_price * 100 if be_price else 0

        self.be_var.set(f"BE Price: ${be_price:.12f}")
        self.tp_var.set(f"TP Price: ${tp_price:.12f}")
        self.meta_var.set(
            f"{percentage_gain:.2f}% gain | Total invested: {money(total_invested)} | Units: {total_units:,.8f}"
        )
        self.last_result = (
            f"Breakeven price: ${be_price:.12f}\n"
            f"Take profit price: ${tp_price:.12f}\n"
            f"Gain: {percentage_gain:.2f}%\n"
            f"Total invested: {money(total_invested)}\n"
            f"Units: {total_units:,.8f}"
        )
        self.on_status("DCA breakeven calculated.")

    def copy_result(self):
        if not self.last_result:
            self.on_status("No DCA result to copy yet.", "warning")
            return
        copy_to_clipboard(self, self.last_result)
        self.on_status("DCA result copied to clipboard.")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(self.purchases, start=1):
            self.tree.insert(
                "",
                tk.END,
                values=(
                    index,
                    money(item["price"]),
                    money(item["amount"]),
                    f"{item['fee']:.4g}",
                    f"{item['units']:,.8f}",
                    money(item["amount"]),
                ),
            )


class DataPlanTab(ttk.Frame):
    display_name = "Data Plan Comparator"

    def __init__(self, parent, on_status):
        super().__init__(parent, padding=18)
        self.on_status = on_status
        self.plans = []
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        input_frame = ttk.Labelframe(self, text="Plan Input", padding=14)
        input_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        self.cost_entry = self._entry(input_frame, "Cost (NGN)", 0)
        self.data_entry = self._entry(input_frame, "Data Size (GB)", 1)
        self.validity_entry = self._entry(input_frame, "Validity (days)", 2)

        buttons = ttk.Frame(input_frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for col in range(2):
            buttons.columnconfigure(col, weight=1)

        actions = (
            ("Add Plan", self.add_plan, "primary"),
            ("Remove Selected", self.remove_selected, "secondary"),
            ("Clear All", self.clear_plans, "warning"),
            ("Compare", self.compare_plans, "success"),
            ("Save Comparison", self.save, "info"),
            ("Load Comparison", self.load, "info-outline"),
        )
        for index, (text, command, style) in enumerate(actions):
            ttk.Button(buttons, text=text, command=command, bootstyle=style).grid(
                row=index // 2, column=index % 2, sticky="ew", padx=5, pady=4
            )

        table_frame = ttk.Labelframe(self, text="Comparison Matrix", padding=10)
        table_frame.grid(row=0, column=1, sticky="nsew")
        table_frame.rowconfigure(1, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.best_var = tk.StringVar(value="Add plans and compare to identify the best value.")
        ttk.Label(table_frame, textvariable=self.best_var, bootstyle="success").grid(row=0, column=0, sticky="w")

        columns = ("index", "cost", "data", "validity", "cost_gb", "cost_day", "score")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)
        labels = {
            "index": "#",
            "cost": "Cost NGN",
            "data": "Data GB",
            "validity": "Validity",
            "cost_gb": "NGN/GB",
            "cost_day": "NGN/day",
            "score": "Score",
        }
        for col in columns:
            self.tree.heading(col, text=labels[col])
            self.tree.column(col, width=105, anchor="e")
        self.tree.column("index", width=45, anchor="center")
        self.tree.tag_configure("best", background="#164b3b")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        self.tree.configure(yscrollcommand=scrollbar.set)

    def _entry(self, parent, label, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        entry = ttk.Entry(parent, justify="right", width=20)
        entry.insert(0, "0")
        entry.bind("<FocusIn>", self.clear_default_text)
        entry.bind("<FocusOut>", self.restore_default_text)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        return entry

    def primary_action(self):
        self.add_plan()

    def can_save(self):
        return True

    def clear_default_text(self, event):
        if event.widget.get() == "0":
            event.widget.delete(0, tk.END)

    def restore_default_text(self, event):
        if not event.widget.get():
            event.widget.insert(0, "0")

    def calculate_score(self, cost, data_size, validity):
        return data_size / cost / validity

    def add_plan(self):
        try:
            cost = parse_float(self.cost_entry, "Cost")
            data_size = parse_float(self.data_entry, "Data size")
            validity = parse_int(self.validity_entry, "Validity")
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc))
            return

        plan = {
            "cost": cost,
            "data": data_size,
            "validity": validity,
            "score": self.calculate_score(cost, data_size, validity),
        }
        self.plans.append(plan)
        for entry in (self.cost_entry, self.data_entry, self.validity_entry):
            entry.delete(0, tk.END)
            entry.insert(0, "0")
        self._refresh_tree()
        self.on_status("Data plan added.")

    def compare_plans(self):
        if not self.plans:
            self.best_var.set("No plans to compare.")
            self.on_status("No plans to compare.", "warning")
            return
        self._refresh_tree()
        best = max(self.plans, key=lambda plan: plan["score"])
        self.best_var.set(
            f"BEST VALUE: NGN {best['cost']:,.2f} | {best['data']:,.2f}GB | "
            f"{best['validity']} days | Score {best['score']:.6f}"
        )
        self.on_status("Data plans compared.")

    def remove_selected(self):
        selected = self.tree.selection()
        if not selected:
            self.on_status("Select a plan to remove.", "warning")
            return
        indexes = sorted((self.tree.index(item) for item in selected), reverse=True)
        for index in indexes:
            self.plans.pop(index)
        self._refresh_tree()
        self.on_status("Selected plan removed.")

    def clear_plans(self):
        self.plans.clear()
        self._refresh_tree()
        self.best_var.set("All plans cleared.")
        self.on_status("All data plans cleared.")

    def save(self):
        if not self.plans:
            self.on_status("No comparison to save.", "warning")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            target = Path(path)
            if target.suffix.lower() == ".json":
                target.write_text(json.dumps(self.plans, indent=2), encoding="utf-8")
            else:
                target.write_text(self._comparison_text(), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save Error", str(exc))
            return
        self.on_status(f"Comparison saved to {Path(path).name}.")

    def load(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            target = Path(path)
            text = target.read_text(encoding="utf-8")
            if target.suffix.lower() == ".json":
                loaded = json.loads(text)
                self.plans = [
                    {
                        "cost": float(item["cost"]),
                        "data": float(item["data"]),
                        "validity": int(item["validity"]),
                        "score": self.calculate_score(float(item["cost"]), float(item["data"]), int(item["validity"])),
                    }
                    for item in loaded
                ]
            else:
                self.plans = self._parse_text_plans(text)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            messagebox.showerror("Load Error", f"Could not load comparison: {exc}")
            return
        self._refresh_tree()
        self.compare_plans()
        self.on_status(f"Comparison loaded from {Path(path).name}.")

    def _comparison_text(self):
        lines = ["Plan Comparison:"]
        for plan in self.plans:
            lines.append(
                f"Cost: NGN {plan['cost']}, Data: {plan['data']}GB, "
                f"Validity: {plan['validity']} days, Score: {plan['score']:.6f}"
            )
        best = max(self.plans, key=lambda plan: plan["score"])
        lines.append("")
        lines.append(
            f"BEST VALUE: Cost: NGN {best['cost']}, Data: {best['data']}GB, "
            f"Validity: {best['validity']} days, Score: {best['score']:.6f}"
        )
        return "\n".join(lines)

    def _parse_text_plans(self, text):
        pattern = re.compile(
            r"Cost:\s*(?:NGN|₦)?\s*([\d.]+),\s*Data:\s*([\d.]+)GB,\s*Validity:\s*(\d+)\s*days",
            re.IGNORECASE,
        )
        plans = []
        for line in text.splitlines():
            if "BEST VALUE" in line.upper() or "MOST COST-EFFECTIVE" in line.upper():
                continue
            match = pattern.search(line)
            if not match:
                continue
            cost, data, validity = match.groups()
            plan = {"cost": float(cost), "data": float(data), "validity": int(validity)}
            plan["score"] = self.calculate_score(plan["cost"], plan["data"], plan["validity"])
            plans.append(plan)
        if not plans:
            raise ValueError("No plan rows found in text file.")
        return plans

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        best_score = max((plan["score"] for plan in self.plans), default=None)
        for index, plan in enumerate(self.plans, start=1):
            tags = ("best",) if best_score is not None and plan["score"] == best_score else ()
            self.tree.insert(
                "",
                tk.END,
                values=(
                    index,
                    f"{plan['cost']:,.2f}",
                    f"{plan['data']:,.2f}",
                    plan["validity"],
                    f"{plan['cost'] / plan['data']:,.2f}",
                    f"{plan['cost'] / plan['validity']:,.2f}",
                    f"{plan['score']:.6f}",
                ),
                tags=tags,
            )


class CompoundInterestTab(ttk.Frame):
    display_name = "Compound Interest"
    frequencies = {
        "Annually": 1,
        "Semi-annually": 2,
        "Quarterly": 4,
        "Monthly": 12,
        "Daily": 365,
    }

    def __init__(self, parent, on_status):
        super().__init__(parent, padding=18)
        self.on_status = on_status
        self.steps = []
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        input_frame = ttk.Labelframe(self, text="Capital Input", padding=14)
        input_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))

        self.principal_entry = self._entry(input_frame, "Principal", 0)
        self.interest_entry = self._entry(input_frame, "Interest Rate (%)", 1)
        self.period_entry = self._entry(input_frame, "Number of Periods", 2)

        ttk.Label(input_frame, text="Compounding Frequency").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=6)
        self.frequency_var = tk.StringVar(value="Annually")
        ttk.Combobox(
            input_frame,
            textvariable=self.frequency_var,
            values=tuple(self.frequencies.keys()),
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="ew", pady=6)

        buttons = ttk.Frame(input_frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for col in range(2):
            buttons.columnconfigure(col, weight=1)
        ttk.Button(buttons, text="Calculate", command=self.calculate, bootstyle="success").grid(
            row=0, column=0, sticky="ew", padx=5, pady=4
        )
        ttk.Button(buttons, text="Show Steps", command=self.show_steps, bootstyle="info").grid(
            row=0, column=1, sticky="ew", padx=5, pady=4
        )
        ttk.Button(buttons, text="Reset", command=self.reset, bootstyle="warning").grid(
            row=1, column=0, sticky="ew", padx=5, pady=4
        )
        ttk.Button(buttons, text="Export CSV", command=self.export_csv, bootstyle="secondary").grid(
            row=1, column=1, sticky="ew", padx=5, pady=4
        )

        result_frame = ttk.Labelframe(self, text="Projection", padding=14)
        result_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 14))
        self.result_var = tk.StringVar(value="Total amount: --")
        self.rate_var = tk.StringVar(value="Effective annual rate: --")
        ttk.Label(result_frame, textvariable=self.result_var, font=RESULT_FONT, bootstyle="success").pack(anchor="w", pady=4)
        ttk.Label(result_frame, textvariable=self.rate_var, bootstyle="info").pack(anchor="w", pady=4)

        table_frame = ttk.Labelframe(self, text="Step Grid", padding=10)
        table_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("period", "amount", "interest", "growth")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=14)
        headings = {
            "period": "Period",
            "amount": "Amount",
            "interest": "Interest Earned",
            "growth": "Total Growth %",
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=160, anchor="e")
        self.tree.column("period", anchor="center", width=80)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def _entry(self, parent, label, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        entry = ttk.Entry(parent, justify="right", width=20)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        return entry

    def primary_action(self):
        self.calculate()

    def calculate(self):
        try:
            principal, rate, periods, frequency = self._inputs()
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc))
            return

        amount = principal * (1 + rate / (100 * frequency)) ** (frequency * periods)
        effective_rate = ((1 + rate / (100 * frequency)) ** frequency - 1) * 100
        self.result_var.set(f"Total amount after {periods} period(s): {money(amount)}")
        self.rate_var.set(f"Nominal: {rate:.4g}% | Effective annual: {effective_rate:.4f}%")
        self.steps = self._calculate_steps(principal, rate, periods, frequency)
        self.on_status("Compound interest calculated.")

    def show_steps(self):
        try:
            principal, rate, periods, frequency = self._inputs()
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc))
            return
        self.steps = self._calculate_steps(principal, rate, periods, frequency)
        self._refresh_tree()
        self.on_status("Compound steps populated.")

    def reset(self):
        for entry in (self.principal_entry, self.interest_entry, self.period_entry):
            entry.delete(0, tk.END)
        self.frequency_var.set("Annually")
        self.result_var.set("Total amount: --")
        self.rate_var.set("Effective annual rate: --")
        self.steps = []
        self._refresh_tree()
        self.principal_entry.focus()
        self.on_status("Compound calculator reset.")

    def export_csv(self):
        if not self.steps:
            self.show_steps()
            if not self.steps:
                return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("period", "amount", "interest", "growth"))
                writer.writeheader()
                writer.writerows(self.steps)
        except OSError as exc:
            messagebox.showerror("Export Error", str(exc))
            return
        self.on_status(f"Compound steps exported to {Path(path).name}.")

    def _inputs(self):
        principal = parse_float(self.principal_entry, "Principal")
        rate = parse_float(self.interest_entry, "Interest rate", allow_zero=True)
        periods = parse_int(self.period_entry, "Number of periods")
        frequency = self.frequencies[self.frequency_var.get()]
        return principal, rate, periods, frequency

    def _calculate_steps(self, principal, rate, periods, frequency):
        steps = []
        for period_number in range(1, periods + 1):
            amount = principal * (1 + rate / (100 * frequency)) ** (frequency * period_number)
            interest = amount - principal
            growth = (interest / principal) * 100
            steps.append(
                {
                    "period": period_number,
                    "amount": round(amount, 2),
                    "interest": round(interest, 2),
                    "growth": round(growth, 4),
                }
            )
        return steps

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for step in self.steps:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    step["period"],
                    money(step["amount"]),
                    money(step["interest"]),
                    f"{step['growth']:.4f}%",
                ),
            )


class PercentChangeTab(ttk.Frame):
    display_name = "Percent Change"

    def __init__(self, parent, on_status):
        super().__init__(parent, padding=18)
        self.on_status = on_status
        self.history = []
        self.last_result = ""
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        input_frame = ttk.Labelframe(self, text="Comparison Input", padding=14)
        input_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        self.old_entry = self._entry(input_frame, "Old Value", 0)
        self.new_entry = self._entry(input_frame, "New Value", 1)

        buttons = ttk.Frame(input_frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for col in range(2):
            buttons.columnconfigure(col, weight=1)
        ttk.Button(buttons, text="Calculate", command=self.calculate_change, bootstyle="success").grid(
            row=0, column=0, sticky="ew", padx=5, pady=4
        )
        ttk.Button(buttons, text="Reset", command=self.reset, bootstyle="warning").grid(
            row=0, column=1, sticky="ew", padx=5, pady=4
        )
        ttk.Button(buttons, text="Copy", command=self.copy_result, bootstyle="info").grid(
            row=1, column=0, sticky="ew", padx=5, pady=4
        )
        ttk.Button(buttons, text="Clear History", command=self.clear_history, bootstyle="secondary").grid(
            row=1, column=1, sticky="ew", padx=5, pady=4
        )

        self.result_var = tk.StringVar(value="Change: --")
        self.diff_var = tk.StringVar(value="Difference: --")
        self.result_label = ttk.Label(input_frame, textvariable=self.result_var, font=RESULT_FONT, bootstyle="info")
        self.result_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(18, 4))
        ttk.Label(input_frame, textvariable=self.diff_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)

        history_frame = ttk.Labelframe(self, text="Mini History", padding=10)
        history_frame.grid(row=0, column=1, sticky="nsew")
        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)

        columns = ("old", "new", "difference", "change")
        self.tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=18)
        for col, label in zip(columns, ("Old", "New", "Difference", "Change")):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=135, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def _entry(self, parent, label, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        entry = ttk.Entry(parent, justify="right", width=20)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        return entry

    def primary_action(self):
        self.calculate_change()

    def calculate_change(self):
        try:
            old = parse_float(self.old_entry, "Old value")
            new = parse_float(self.new_entry, "New value", allow_zero=True)
        except ValueError as exc:
            messagebox.showerror("Input Error", str(exc))
            return

        difference = new - old
        change = (difference / old) * 100
        if change < 0:
            prefix = "🔻"
            style = "danger"
            diff_text = f"{difference:.2f}"
        elif change > 0:
            prefix = "🔺"
            style = "success"
            diff_text = f"+{difference:.2f}"
        else:
            prefix = "➖"
            style = "info"
            diff_text = "0.00"

        self.result_var.set(f"Change: {prefix} {change:.2f}%")
        self.diff_var.set(f"Difference: {diff_text}")
        self.result_label.configure(bootstyle=style)
        self.last_result = f"Old: {old}\nNew: {new}\nDifference: {diff_text}\nChange: {change:.2f}%"
        self.history.insert(0, {"old": old, "new": new, "difference": difference, "change": change})
        self.history = self.history[:20]
        self._refresh_tree()
        self.on_status("Percent change calculated.")

    def reset(self):
        self.old_entry.delete(0, tk.END)
        self.new_entry.delete(0, tk.END)
        self.result_var.set("Change: --")
        self.diff_var.set("Difference: --")
        self.result_label.configure(bootstyle="info")
        self.old_entry.focus()
        self.on_status("Percent inputs reset.")

    def copy_result(self):
        if not self.last_result:
            self.on_status("No percent-change result to copy yet.", "warning")
            return
        copy_to_clipboard(self, self.last_result)
        self.on_status("Percent-change result copied.")

    def clear_history(self):
        self.history.clear()
        self._refresh_tree()
        self.on_status("Percent-change history cleared.")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.history:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    f"{item['old']:,.2f}",
                    f"{item['new']:,.2f}",
                    f"{item['difference']:,.2f}",
                    f"{item['change']:.2f}%",
                ),
            )


class SciFiCalculatorSuite:
    def __init__(self):
        self.root = ttk.Window(themename="cyborg")
        self.root.title(f"{APP_TITLE} - {APP_COPYRIGHT}")
        self.root.minsize(960, 720)
        self.style = ttk.Style()
        self.header_font = safe_font("Orbitron", "Segoe UI", 22, "bold")
        self.subtitle_font = safe_font("Cascadia Mono", "Consolas", 11)
        self.tabs = []
        self.theme_var = tk.StringVar(value="cyborg")
        self._build_menu()
        self._build_layout()
        self._center()
        self._bind_active_tab()

    def _build_menu(self):
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Save", command=self.save_active)
        file_menu.add_command(label="Load", command=self.load_active)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menu_bar, tearoff=0)
        theme_menu = tk.Menu(view_menu, tearoff=0)
        for theme in THEMES:
            theme_menu.add_radiobutton(
                label=theme.title(),
                value=theme,
                variable=self.theme_var,
                command=lambda name=theme: self.change_theme(name),
            )
        view_menu.add_cascade(label="Theme", menu=theme_menu)
        menu_bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu_bar)

    def _build_layout(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=(18, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_TITLE, font=self.header_font, bootstyle="info").grid(row=0, column=0, sticky="w")
        self.subtitle_var = tk.StringVar(value="DCA Breakeven")
        ttk.Label(header, textvariable=self.subtitle_var, font=self.subtitle_font, bootstyle="secondary").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Label(header, text=APP_COPYRIGHT, font=self.subtitle_font, bootstyle="secondary").grid(
            row=2, column=0, sticky="w", pady=(2, 0)
        )

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))

        self.tabs = [
            DCABreakevenTab(self.notebook, self.set_status),
            DataPlanTab(self.notebook, self.set_status),
            CompoundInterestTab(self.notebook, self.set_status),
            PercentChangeTab(self.notebook, self.set_status),
        ]
        labels = ("DCA & BE", "Data", "Compound", "% Change")
        for tab, label in zip(self.tabs, labels):
            self.notebook.add(tab, text=label)

        self.status_var = tk.StringVar(value="Ready.")
        self.status_label = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", padding=6)
        self.status_label.grid(row=2, column=0, sticky="ew")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.root.bind("<Control-Return>", self._secondary_action)

    def _center(self):
        self.root.update_idletasks()
        width = 1020
        height = 760
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 2
        self.root.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")

    def _active_tab(self):
        selected = self.notebook.select()
        return self.root.nametowidget(selected) if selected else self.tabs[0]

    def _bind_active_tab(self):
        self.root.unbind("<Return>")
        self.root.bind("<Return>", lambda event: self._active_tab().primary_action())

    def _secondary_action(self, _event=None):
        tab = self._active_tab()
        action = getattr(tab, "secondary_action", None)
        if action:
            action()
        else:
            tab.primary_action()

    def _on_tab_changed(self, _event=None):
        tab = self._active_tab()
        self.subtitle_var.set(tab.display_name)
        self._bind_active_tab()
        self.set_status(f"{tab.display_name} module active.")

    def set_status(self, message, kind="info"):
        prefixes = {"info": "INFO", "warning": "WARN", "error": "ERROR", "success": "OK"}
        self.status_var.set(f"{prefixes.get(kind, 'INFO')}: {message}")

    def save_active(self):
        tab = self._active_tab()
        save = getattr(tab, "save", None)
        if callable(save):
            save()
        else:
            self.set_status("Save is not supported for this module.", "warning")

    def load_active(self):
        tab = self._active_tab()
        load = getattr(tab, "load", None)
        if callable(load):
            load()
        else:
            self.set_status("Load is not supported for this module.", "warning")

    def change_theme(self, theme):
        self.style.theme_use(theme)
        self.theme_var.set(theme)
        self.set_status(f"Theme switched to {theme}.")

    def show_about(self):
        messagebox.showinfo(
            "About",
            "NEXUS Calculator Suite\n\n"
            "A multi-tab Tkinter suite for DCA breakeven, data plans, compound interest, and percent change.\n\n"
            f"Author: {APP_AUTHOR}\n"
            f"{APP_COPYRIGHT}",
        )

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SciFiCalculatorSuite().run()
