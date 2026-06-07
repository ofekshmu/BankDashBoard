import os
import webbrowser
from datetime import datetime, date
from typing import Optional

from database import DataBase
from src_utils.utils import utils


class GymSplitter:

    DEFAULT_PRICE = 25.0
    HTML_OUTPUT   = os.path.join("source", "html", "gym_output.html")
    HTML_TEMPLATE = os.path.join("source", "html", "gym_template.html")

    def __init__(self):
        self.db = DataBase()

    # ------------------------------------------------------------------ #
    #  Main menu                                                           #
    # ------------------------------------------------------------------ #

    def menu(self):
        while True:
            choice = utils.template_menu(
                options=[
                    "Record new gym session",
                    "View report (open in browser)",
                    "Manage participants",
                    "Recommend next payer",
                ],
                msg="Gym Expense Splitter",
                exit=True,
                col_space=36,
            )
            match choice:
                case 0:
                    return
                case 1:
                    self.record_session()
                case 2:
                    self.generate_html_report()
                    webbrowser.open(os.path.abspath(self.HTML_OUTPUT))
                case 3:
                    self.manage_participants()
                case 4:
                    self._print_recommendation()
                case _:
                    utils.log("Please insert a valid number.", "system")

    # ------------------------------------------------------------------ #
    #  Record session                                                      #
    # ------------------------------------------------------------------ #

    def record_session(self):
        participants_df = self.db.gym_get_all_participants(active_only=True)
        if participants_df.empty:
            utils.log("No active participants. Add participants first (Manage participants).", "warning")
            return

        # Date
        today = date.today().strftime("%Y-%m-%d")
        session_date = input(f"Date (YYYY-MM-DD) [{today}]: ").strip()
        if not session_date:
            session_date = today
        if not self._valid_date(session_date):
            utils.log("Invalid date format. Using today.", "warning")
            session_date = today

        # Select attendees
        utils.log("\nActive participants:", "system")
        for i, row in participants_df.iterrows():
            print(f"  {i + 1} -> {row['name']}")

        attendee_ids = self._multi_select(participants_df, "Select attendees (comma-separated numbers, e.g. 1,2): ")
        if not attendee_ids:
            utils.log("No attendees selected. Cancelled.", "warning")
            return
        attendee_names = [participants_df.loc[participants_df["id"] == pid, "name"].values[0] for pid in attendee_ids]

        # Price
        last_price = self.db.gym_get_last_price()
        default_price = last_price if last_price else self.DEFAULT_PRICE
        price_input = input(f"Price per person [₪{default_price:.2f}]: ").strip()
        try:
            product_price = float(price_input) if price_input else default_price
            if product_price <= 0:
                raise ValueError
        except ValueError:
            utils.log(f"Invalid price. Using ₪{default_price:.2f}.", "warning")
            product_price = default_price

        # Recommended payer
        recommendation = self.recommend_payer()
        if recommendation:
            utils.log(f"\n★  Recommended payer: {recommendation['name']}  (net balance: {recommendation['net']:+.2f}₪)", "system")

        # Select payer
        utils.log("\nWho paid?", "system")
        for idx, (pid, name) in enumerate(zip([r["id"] for _, r in participants_df.iterrows()],
                                              [r["name"] for _, r in participants_df.iterrows()]), start=1):
            print(f"  {idx} -> {name}")

        payer_id = self._single_select(participants_df, "Select payer: ")
        if payer_id is None:
            utils.log("No payer selected. Cancelled.", "warning")
            return

        # Notes
        notes = input("Notes (optional): ").strip()

        # Persist (atomic: session + all participants in one transaction)
        session_id = self.db.gym_insert_session_with_participants(
            session_date, product_price, payer_id, notes, attendee_ids
        )

        payer_name = participants_df.loc[participants_df["id"] == payer_id, "name"].values[0]
        # Payer may have been auto-added to attendees, so count unique
        total = product_price * len(set(attendee_ids) | {payer_id})
        utils.log(
            f"\n✓ Session recorded — {session_date} | "
            f"Attendees: {', '.join(attendee_names)} | "
            f"Payer: {payer_name} | "
            f"Total: ₪{total:.2f}",
            "system",
        )

    # ------------------------------------------------------------------ #
    #  Manage participants                                                  #
    # ------------------------------------------------------------------ #

    def manage_participants(self):
        while True:
            choice = utils.template_menu(
                options=["Add participant", "Rename participant", "Toggle active/inactive"],
                msg="Manage Participants",
                exit=True,
                col_space=30,
            )
            match choice:
                case 0:
                    return
                case 1:
                    name = input("Participant name: ").strip()
                    if name:
                        pid = self.db.gym_add_participant(name)
                        utils.log(f"✓ Added '{name}' (id={pid})", "system")
                    else:
                        utils.log("Name cannot be empty.", "warning")
                case 2:
                    df = self.db.gym_get_all_participants()
                    if df.empty:
                        utils.log("No participants yet.", "warning")
                        continue
                    self._print_participants(df)
                    pid = self._pick_participant_id(df, "Rename participant #: ")
                    if pid is None:
                        continue
                    new_name = input("New name: ").strip()
                    if new_name:
                        self.db.gym_rename_participant(pid, new_name)
                        utils.log(f"✓ Renamed to '{new_name}'", "system")
                case 3:
                    df = self.db.gym_get_all_participants()
                    if df.empty:
                        utils.log("No participants yet.", "warning")
                        continue
                    self._print_participants(df)
                    pid = self._pick_participant_id(df, "Toggle participant #: ")
                    if pid is None:
                        continue
                    current = int(df.loc[df["id"] == pid, "is_active"].values[0])
                    new_state = not bool(current)
                    self.db.gym_set_participant_active(pid, new_state)
                    status = "active" if new_state else "inactive"
                    name = df.loc[df["id"] == pid, "name"].values[0]
                    utils.log(f"✓ '{name}' is now {status}.", "system")
                case _:
                    utils.log("Please insert a valid number.", "system")

    # ------------------------------------------------------------------ #
    #  Debt calculation & recommendation                                   #
    # ------------------------------------------------------------------ #

    def calculate_debts(self) -> dict:
        df = self.db.gym_get_debt_summary()
        return {row["name"]: row["net_balance"] for _, row in df.iterrows()}

    def recommend_payer(self) -> Optional[dict]:
        df = self.db.gym_get_debt_summary()
        if df.empty:
            return None
        row = df.iloc[0]  # lowest net_balance first (ordered by ASC in query)
        return {"name": row["name"], "net": row["net_balance"]}

    def _print_recommendation(self):
        rec = self.recommend_payer()
        if rec:
            utils.log(f"★  Recommended next payer: {rec['name']}  (net balance: {rec['net']:+.2f}₪)", "system")
        else:
            utils.log("No sessions recorded yet.", "system")

    # ------------------------------------------------------------------ #
    #  HTML report generation                                              #
    # ------------------------------------------------------------------ #

    def generate_html_report(self):
        try:
            import bs4
        except ImportError:
            import subprocess, sys
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'beautifulsoup4'])
            import bs4

        with open(self.HTML_TEMPLATE, "r", encoding="utf-8") as f:
            soup = bs4.BeautifulSoup(f.read(), "html.parser")

        # Update date
        date_span = soup.find("span", class_="update-date")
        if date_span:
            date_span.string = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Member summary cards
        debt_df = self.db.gym_get_debt_summary()
        members_grid = soup.find("section", id="members-grid")
        if members_grid:
            members_grid.clear()
            accent_colors = ["#1DB954", "#509bf5", "#c862e0", "#f59c1a", "#e05a5a"]
            for i, row in debt_df.iterrows():
                color = accent_colors[i % len(accent_colors)]
                card = soup.new_tag("div", attrs={"class": "member-card"})
                card["style"] = f"border-top-color: {color};"

                avatar = soup.new_tag("div", attrs={"class": "member-avatar"})
                avatar["style"] = f"background: {color}; color: {'#000' if color in ['#1DB954','#f59c1a'] else '#fff'};"
                avatar.string = row["name"][0].upper()
                card.append(avatar)

                name_tag = soup.new_tag("div", attrs={"class": "member-name"})
                name_tag.string = row["name"]
                card.append(name_tag)

                for label, value, css_val in [
                    ("Sessions attended", int(row["sessions_attended"]), "neutral"),
                    ("Total paid out", f"₪{row['total_paid_out']:.2f}", "neutral"),
                    ("Fronted for others", f"₪{row['total_fronted']:.2f}", "positive" if row["total_fronted"] > 0 else "neutral"),
                    ("Owes to others", f"₪{row['total_owed']:.2f}", "negative" if row["total_owed"] > 0 else "neutral"),
                ]:
                    stat = soup.new_tag("div", attrs={"class": "member-stat"})
                    lbl = soup.new_tag("span")
                    lbl.string = label
                    val = soup.new_tag("span", attrs={"class": f"val {css_val}"})
                    val.string = str(value)
                    stat.append(lbl)
                    stat.append(val)
                    card.append(stat)

                net = row["net_balance"]
                net_stat = soup.new_tag("div", attrs={"class": "member-stat"})
                net_lbl = soup.new_tag("span")
                net_lbl.string = "Net balance"
                net_cls = "positive" if net > 0 else ("negative" if net < 0 else "neutral")
                net_val = soup.new_tag("span", attrs={"class": f"val {net_cls}"})
                net_val.string = f"₪{net:+.2f}"
                net_stat.append(net_lbl)
                net_stat.append(net_val)
                card.append(net_stat)

                members_grid.append(card)

        # Recommendation banner
        banner = soup.find("section", id="recommendation-banner")
        rec = self.recommend_payer()
        if banner and rec:
            name_div = banner.find("div", class_="rec-name")
            if name_div:
                name_div.string = rec["name"]
            detail_div = banner.find("div", class_="rec-detail")
            if detail_div:
                detail_div.string = f"Net balance: ₪{rec['net']:+.2f} — pays next"

        # Debt table
        debt_body = soup.find("tbody", id="debt-body")
        if debt_body:
            debt_body.clear()
            for _, row in debt_df.iterrows():
                tr = soup.new_tag("tr")
                for text, extra_class in [
                    (row["name"], ""),
                    (f"₪{row['total_fronted']:.2f}", "positive" if row["total_fronted"] > 0 else ""),
                    (f"₪{row['total_owed']:.2f}", "negative" if row["total_owed"] > 0 else ""),
                    (f"₪{row['net_balance']:+.2f}", "positive" if row["net_balance"] > 0 else ("negative" if row["net_balance"] < 0 else "")),
                    (f"₪{row['total_paid_out']:.2f}", ""),
                    (str(int(row["sessions_attended"])), ""),
                ]:
                    td = soup.new_tag("td", attrs={"class": extra_class} if extra_class else {})
                    td.string = str(text)
                    tr.append(td)
                debt_body.append(tr)

        # Session history
        sessions_df = self.db.gym_get_all_sessions()
        sessions_body = soup.find("tbody", id="sessions-body")
        if sessions_body:
            sessions_body.clear()
            if sessions_df.empty:
                tr = soup.new_tag("tr")
                td = soup.new_tag("td", attrs={"colspan": "7", "style": "text-align:center; color: var(--text-muted);"})
                td.string = "No sessions recorded yet."
                tr.append(td)
                sessions_body.append(tr)
            else:
                for _, srow in sessions_df.iterrows():
                    part_df = self.db.gym_get_session_participants(int(srow["id"]))
                    attendees = ", ".join(part_df["name"].tolist()) if not part_df.empty else "—"
                    total = srow["product_price"] * srow["participant_count"]
                    tr = soup.new_tag("tr")
                    cells = [
                        str(srow["id"]),
                        srow["date"],
                        attendees,
                        "",  # payer badge handled below
                        f"₪{srow['product_price']:.2f}",
                        f"₪{total:.2f}",
                        srow["notes"] if srow["notes"] else "",
                    ]
                    for idx, text in enumerate(cells):
                        td = soup.new_tag("td")
                        if idx == 3:
                            badge = soup.new_tag("span", attrs={"class": "payer-badge"})
                            badge.string = srow["payer_name"]
                            td.append(badge)
                        else:
                            td.string = text
                        tr.append(td)
                    sessions_body.append(tr)

        with open(self.HTML_OUTPUT, "w", encoding="utf-8") as f:
            f.write(str(soup.prettify()))

        utils.log(f"✓ Report generated: {self.HTML_OUTPUT}", "system")

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _valid_date(self, s: str) -> bool:
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _multi_select(self, df, prompt: str) -> list:
        """Returns list of participant IDs selected by 1-based index."""
        ids = list(df["id"])
        while True:
            raw = input(prompt).strip()
            if not raw:
                return []
            try:
                indices = [int(x.strip()) for x in raw.split(",")]
                selected = []
                valid = True
                for idx in indices:
                    if idx < 1 or idx > len(ids):
                        utils.log(f"Index {idx} out of range.", "warning")
                        valid = False
                        break
                    selected.append(ids[idx - 1])
                if valid and selected:
                    return selected
            except ValueError:
                utils.log("Please enter comma-separated numbers.", "warning")

    def _single_select(self, df, prompt: str) -> Optional[int]:
        """Returns a single participant ID selected by 1-based index."""
        ids = list(df["id"])
        while True:
            raw = input(prompt).strip()
            if not raw:
                return None
            if raw.isnumeric():
                idx = int(raw)
                if 1 <= idx <= len(ids):
                    return ids[idx - 1]
            utils.log("Please enter a valid number.", "warning")

    def _print_participants(self, df):
        utils.log("Participants:", "system")
        for i, row in df.iterrows():
            status = "active" if row["is_active"] else "inactive"
            print(f"  {i + 1} -> {row['name']} ({status})")

    def _pick_participant_id(self, df, prompt: str) -> Optional[int]:
        ids = list(df["id"])
        while True:
            raw = input(prompt).strip()
            if not raw:
                return None
            if raw.isnumeric():
                idx = int(raw)
                if 1 <= idx <= len(ids):
                    return ids[idx - 1]
            utils.log("Invalid selection.", "warning")
