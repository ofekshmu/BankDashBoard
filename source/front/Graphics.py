import matplotlib
matplotlib.use('Agg')  # non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils
import seaborn as sns
from Constants import GENERAL_PLOT
from Constants import Local, Paths
from typing import Tuple
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime


class Graphics:


    @staticmethod
    def _create_empty_chart(pie_name: str):
        """Helper method to create an empty chart when no data is present"""
        _, ax = plt.subplots()
        ax.pie([], labels=[])
        ax.set_title('Empty Pie Chart')
        plt.savefig(f'Outputs\\{pie_name}_category.png')
        plt.savefig(f'Outputs\\{pie_name}_prices.png')

    @staticmethod
    def plot_transactions_pie_chart(df: pd.DataFrame, pie_name: str, color_set: list) -> list:
        """
        Create and save two pie charts for transaction data analysis.
        
        Args:
            df (pd.DataFrame): Transaction data with columns ['Final_Value', 'Category', 'Name', 'Description/Charge_Currency']
            pie_name (str): Name of the chart (must be one of: "Investments", "Spendings", "Earnings")
            color_set (list): List of hex color codes for the chart
            
        Returns:
            list: List of transactions identified as outliers
            
        Saves two files:
            - {pie_name}_category.png: Pie chart showing category distribution
            - {pie_name}_prices.png: Pie chart showing price distribution
        """
        VALID_CHART_TYPES = ["Investments", "Spendings", "Earnings"]
        DONUT_HOLE_SIZE = 0.70
        FIG_SIZE = (7, 5)

        def create_donut_chart(ax, df, title, total_value):
            """Helper function to create a donut chart with consistent styling"""
            my_circle = plt.Circle((0, 0), DONUT_HOLE_SIZE, fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(my_circle)
            
            # Add center text
            centre_text = f"{total_value:,.2f} ₪"
            ax.text(0, 0, centre_text,
                    horizontalalignment='center',
                    verticalalignment='center',
                    fontsize=22,
                    fontweight='bold',
                    color='black',
                    fontname='Arial')
            
            ax.set_title(title, fontsize = 20)
            ax.set_ylabel('')

        if pie_name not in VALID_CHART_TYPES:
            utils.log(f"pie_name must be one of {VALID_CHART_TYPES}", 'error')

        outliers_list = []

        if df.empty:
            Graphics._create_empty_chart(pie_name)  # Create an empty chart
            return []     

        # Preprocessing    
        df = df.copy()
        df['Final_Value'] = df['Final_Value'].abs()
        total_value = df['Final_Value'].sum()
        
        # -------------- Create a pie chart with category names --------------
        df_names = df.copy()

        if pie_name in ["Spendings", "Earnings"]:
            df_names.index = df_names.index.map(lambda name: f"{utils.heb_conversion(name)}")
            df_names, outliers_list = utils.seperate_high_std(df_names, 'Final_Value')
        elif pie_name == "Investments":
            def get_display_name(row) -> str:
                """Helper function to determine the display name for pie chart labels"""
                if row['Description'] is None:
                    base_text = row['Name']
                else:
                    base_text = row['Description']
                
                return utils.heb_conversion(str(base_text))
            df_names = df_names.set_index(df_names.apply(get_display_name, axis=1))

        # Create category pie chart
        ax = df_names.plot.pie(y='Final_Value',
                            figsize=FIG_SIZE,
                            legend=False,
                            title=pie_name,
                            colors=color_set)
        create_donut_chart(ax, df_names, pie_name, total_value)
        plt.savefig(f'Outputs\\{pie_name}_category.png')
        plt.close()

        # Create prices pie chart
        prices_df = df.copy()
        prices_df.index = df.index.map(lambda name: f"{prices_df.loc[name,'Final_Value']:,.2f}₪")

        if pie_name in ["Spendings", "Earnings"]:
            prices_df, _ = utils.seperate_high_std(prices_df, 'Final_Value')

        ax = prices_df.plot.pie(y='Final_Value',
                                    figsize=FIG_SIZE,
                                    legend=False,
                                    title=pie_name,
                                    colors=color_set)
        create_donut_chart(ax, prices_df, pie_name, total_value)
        plt.savefig(f'Outputs\\{pie_name}_prices.png')
        plt.close()
        
        return outliers_list

    @staticmethod
    def plot_general(spendings: list, 
                     spendings_overall: list,
                     earnings: list,
                     topic: str = "",
                     title_ext: str = "",
                     lp_Overall_income: bool = True,
                     lp_user_defined: bool = False,
                     user_spendings_sum: list = [],
                     user_earnings_sum: list = [],
                     fig_size=(14, 8)):
        """
        Plot general financial statistics showing spendings, earnings and overall income.
        
        Args:
            spendings (list): Monthly spending values
            spendings_overall (list): Monthly net income values across all accounts
            earnings (list): Monthly earning values
            title_ext (str, optional): Extension for output filename. Defaults to "".
            fig_size (tuple, optional): Figure dimensions. Defaults to (14, 8).
        
        Saves:
            PNG file at 'Outputs/General_info{title_ext}.png'
        """
        # Constants
        COLORS = {
            'spendings': "#f66b85",
            'investments': "#DAA520", 
            'earnings': "#4fba89",
            'net_income': "#58063f",
            'user_defined': "#99303f"
        }
        FONT_SIZES = {
            'title': 18,
            'labels': 16,
            'annotations': 10
        }
        OFFSET_FACTOR = 0.035

        def get_last_n_months_names(n_months: int) -> list:
            """Get list of last n month names."""
            delta = 0 if GENERAL_PLOT.SHOW_CURRENT_MONTH else 1
            current_month = (datetime.now() - pd.DateOffset(months=delta)).month
            return [(datetime(2023, (current_month - i) % 12 or 12, 1)).strftime('%B') 
                    for i in range(n_months)]

        def prepare_plot_data(months: list) -> dict:
            """Prepare DataFrames for plotting."""
            data = {}
            
            # Base data
            base_df = pd.DataFrame({
                "Months": months, 
                "Spendings": spendings, 
                "Earnings": earnings
            })
            
            # Investment data
            investment_values = np.array(spendings) - np.array(spendings_overall)
            invest_df = pd.DataFrame({
                "Months": months, 
                "Spendings": investment_values, 
                "Earnings": earnings
            })
            
            from Constants import INVESTMENT_CATEGORY
            # Used for when category analysis for "Investments" is selected
            spendings_overall_option = [0] * len(earnings) if topic == INVESTMENT_CATEGORY else spendings_overall

            # Overall income data
            if lp_Overall_income:
                data["overall_df"] = pd.DataFrame({
                                        "Months": months, 
                                        "Overall Income": [x + y for x, y in zip(earnings, spendings_overall_option)]
                                    })

            # user defined plot
            if lp_user_defined:
                data["user_defined_df"] = pd.DataFrame({
                                            "Months": months, 
                                            "Overall Income": [x + y for x, y in zip(user_earnings_sum, user_spendings_sum)]
                                        })
            

            data["base_df"] = pd.melt(base_df, id_vars=["Months"], var_name="Category", value_name="Amount")
            data["invest_df"] = pd.melt(invest_df, id_vars=["Months"], var_name="Category", value_name="Amount")
            
            return data

        def create_legend_handles() -> list:
            """Create legend handles for the plot."""
            return [
                mpatches.Patch(color=COLORS['spendings'], label='Spendings'),
                mpatches.Patch(color=COLORS['earnings'], label='Earnings'),
                mpatches.Patch(color=COLORS['investments'], label='Spendings (Investments)'),
                mpatches.Patch(color=COLORS['net_income'], label='Overall Net Income', linestyle='--')
            ]

        def add_value_annotations(ax, data_df: pd.DataFrame, color: str) -> None:
            """Add value annotations to the line plot."""
            # Filter out rows with NaN values in 'Overall Income'
            for x, y in zip(data_df['Months'], data_df['Overall Income']):
                ax.annotate(f'{y:,.0f}₪',
                        xy=(x, y),
                        xytext=(0, 10),  # 10 points vertical offset
                        textcoords="offset points",
                        ha='center',
                        va='bottom',
                        color=color,
                        fontweight='bold')

        # Main plotting logic
        months = get_last_n_months_names(len(spendings))
        data = prepare_plot_data(months)
        
        # Create plot
        sns.set(style="whitegrid")
        _, ax = plt.subplots(figsize=fig_size)
                
        # Plot layers
        sns.barplot(x="Months", y="Amount", hue="Category", 
                    data=data["base_df"][::-1], ax=ax, 
                    palette=[COLORS['earnings'], COLORS['spendings']])
        
        if not lp_user_defined:
            sns.barplot(x="Months", y="Amount", hue="Category", 
                        data=data["invest_df"][::-1], ax=ax,
                        palette=[COLORS['earnings'], COLORS['investments']])
            
        if lp_Overall_income:
            sns.lineplot(x="Months", y="Overall Income", 
                        data=data["overall_df"], ax=ax,
                        color=COLORS['net_income'],
                        marker='o', linestyle='--')
            add_value_annotations(ax, data["overall_df"], COLORS['net_income'])
        
        if lp_user_defined:
            sns.lineplot(x="Months", y="Overall Income", 
                        data=data["user_defined_df"], ax=ax,
                        color=COLORS['user_defined'],
                        marker='o', linestyle='--')

            add_value_annotations(ax, data["user_defined_df"], COLORS['user_defined'])

        # Styling
        ax.legend(handles=create_legend_handles())
        ax.set_xlabel("Months", fontsize=FONT_SIZES['labels'])
        ax.set_ylabel("Amount (₪)", fontsize=FONT_SIZES['labels'])
        ax.set_title(f"Monthly Spendings and Earnings {title_ext}", fontsize=FONT_SIZES['title'])
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, tick_number: f'{value:,.0f}₪' ))

        # Save plot
        output_path = f'Outputs\\General_info{"_" + title_ext if title_ext else ""}.png'
        plt.savefig(output_path, bbox_inches='tight')
        plt.close()

    @staticmethod
    def card_distribution(color_dict: dict, df_card_status: pd.DataFrame):
        """
        Revceives the spending df of the current month,
        """
        if not df_card_status.empty:
            # i want to show the absolute values of the spending in the graph
            df_card_status['Final_Value'] = df_card_status.apply(lambda row: abs(row['Final_Value']), axis=1)

            # Plot the bar plot using seaborn
            sns.set(style="whitegrid")
            plt.figure(figsize=(6, 3))

            # Adding the values on top of the bar plots:
            ax = sns.barplot(x="CardID", hue="CardID", y="Final_Value", data=df_card_status, palette=color_dict)
            ax.get_legend().remove() if ax.get_legend() else None
            data_index = 0
            for p in ax.patches:
                height = p.get_height()
                if height == 0 or p.get_width() == 0:
                    continue
                if data_index >= len(df_card_status):
                    break
                status = df_card_status['Status'].iloc[data_index]
                card_id = df_card_status['CardID'].iloc[data_index]
                data_index += 1
                # ------------ annotate the value of the bar on top of it ------------
                ax.annotate(f'{height:,.0f}₪',
                            xy=(p.get_x() + p.get_width() / 2, height),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom', fontweight='bold')
                # ------------ ignore annotation for bank row ------------------------
                if card_id == "Bank":
                    continue
                # ------------ annotate "Verified" Text ------------------------------
                if status:
                    ax.annotate('Verified',
                                xy=(p.get_x() + p.get_width() / 2, height),
                                xytext=(0, 17),  # 3 points vertical offset
                                textcoords="offset points",
                                ha='center', va='bottom', fontweight='bold', color = 'green')
                # --------------------------------------------------------------------
                if not status:
                    ax.annotate('Not Verified',
                                xy=(p.get_x() + p.get_width() / 2, height),
                                xytext=(0, 17),  # 3 points vertical offset
                                textcoords="offset points",
                                ha='center', va='bottom', fontweight='bold', color = 'red')
                    

            # The following section is responsible for changing the y label values
            # for better visual - Custom formatter for y-axis
            # -----------------------------------------------------------------------
            import matplotlib.ticker as ticker
            def format_ils(value, tick_number):
                return f'{value:,.0f}₪'

            # Apply custom formatter to y-axis
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(format_ils))
            # -----------------------------------------------------------------------
            # ax.set_xlabel("Card no'/Bank")
            # ax.set_ylabel("Amount")
            ax.set_title("Source Distribution")
            
        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_ylabel('')
            # set the title of the plot
            ax.set_title('Empty Chart')

        plt.savefig(r'Outputs\Card_Distribution.png')

    @staticmethod
    def plot_pie_distribution(df: pd.DataFrame) -> list:
        """
        The function receives a 'process_prices_ready' data frame and creates a distribution pie chart
        according to its index values. The pie chart is displayed with percentage values and index names.
        The chart will show entries below a certain treshold as 'other' and the following will be returned as
        a list. the outliers are marked according to the 'cover_outliers' function.
        """

        def cover_outliers(df) -> Tuple[pd.DataFrame, pd.DataFrame]:
            """
            The 'cover_outliers' replaces entries in the given input @df, that do not pass the threshold value,
            with a single entry that sums all of them. the index of the new intery will be named 'other'.
            The function will return the newly created df and another df that represents the removed entries.
            """
            numerical_col_name = 'Final_Value'

            total = df[numerical_col_name].sum()

            lower_treshold = total*0.02
            #lower_treshold = lower_treshold if lower_treshold > 0 else 0.05*mean 

            high_treshold = df[numerical_col_name].max()  + 10
            
            outliers_df = df[(df[numerical_col_name] > high_treshold) | (df[numerical_col_name] < lower_treshold)]
            
            if not outliers_df.empty:
                df.index = df.index.map(lambda x: "אחר" if df.loc[x, numerical_col_name] > high_treshold or df.loc[x, numerical_col_name] < lower_treshold else x)

                # Step 1: Filter out the rows where the index is "אחר"
                removed_rows = df.loc[df.index == "אחר"]

                # Step 2: Calculate the sum of the 'Final_Value' column for the removed rows
                sum_removed = removed_rows['Final_Value'].sum()

                # Step 3: Remove the rows from the original DataFrame
                df = df.drop(index="אחר")

                # Step 4: Add a new row with the sum
                df.loc['אחר'] = sum_removed


            return df, outliers_df
    
        outliers_lst = []

        if not df.empty:
            df['Final_Value'] = df.apply(lambda row: abs(row['Final_Value']), axis=1)
            df, outliers_df = cover_outliers(df)
            outliers_lst = outliers_df.index.tolist()
            df['Percent'] = df.apply(lambda row: abs(row['Final_Value'])*100/df['Final_Value'].sum(), axis=1)
            df.index = df.index.map(lambda x: f"{utils.heb_conversion(x)}\n{df.loc[x, 'Percent']:,.2f}%")

            ax = df.plot.pie(y='Final_Value', figsize=(5, 3), legend=False, title="Distribution", colors=Local.Colors)
            ax.set_ylabel('')

        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_ylabel('')
            # set the title of the plot
            ax.set_title('Empty Pie Chart')

        plt.savefig(r'Outputs\Category_Distribution.png')
        return outliers_lst
    
    @staticmethod
    def plot_linear_plots_graph(data_dict: dict, projected_data: dict = None) -> None:
        """Plot line graphs for account balances over time with value annotations.
        projected_data: dict of {account_name: [(date, value), ...]} drawn as dashed lines.
        """
        sns.set(style="whitegrid")
        plt.figure(figsize=(18, 8))

        import re as _re
        def _label(s):
            """Apply _heb() only to strings containing Hebrew characters."""
            return Graphics._heb(s) if _re.search(r'[\u05d0-\u05ea]', s) else s

        color_cycle = plt.rcParams['axes.prop_cycle'].by_key()['color']
        account_colors = {}

        # Plot historical (solid) lines
        for i, (key, value) in enumerate(data_dict.items()):
            if not value:
                continue
            x, y = zip(*value)
            color = color_cycle[i % len(color_cycle)]
            account_colors[key] = color
            line = plt.plot(x, y, label=_label(key), marker='o', color=color)[0]

            for xi, yi in zip(x, y):
                plt.annotate(f'{yi:,.0f}₪',
                             (xi, yi),
                             xytext=(0, 10),
                             textcoords='offset points',
                             ha='center', va='bottom',
                             color=line.get_color(),
                             fontsize=8)

        # Plot projected (dashed) lines using same color as parent account
        if projected_data:
            for key, value in projected_data.items():
                if not value:
                    continue
                x, y = zip(*value)
                color = account_colors.get(key, 'gray')
                plt.plot(x, y,
                         label=_label(f'{key} (תחזית)'),
                         linestyle='--',
                         marker='',
                         color=color,
                         alpha=0.6)
                # Annotate only last point
                plt.annotate(f'{y[-1]:,.0f}₪',
                             (x[-1], y[-1]),
                             xytext=(0, 10),
                             textcoords='offset points',
                             ha='center', va='bottom',
                             color=color,
                             fontsize=8)

        plt.legend()
        plt.xticks(rotation=45)
        plt.title("Account Balances Over Time", fontsize=20, pad=20)
        plt.xlabel("Date")
        plt.ylabel("Balance (₪)")
        plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:,.0f}₪'))
        plt.tight_layout()
        plt.savefig(r'Outputs\accounts_liner_plots.png')
        plt.close()


    @staticmethod
    def generate_payment_pie_graphs(monthly_payments_df: pd.DataFrame) -> None:

        import matplotlib.pyplot as plt

        if monthly_payments_df.empty:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_title('No Payments Data for this month')
            plt.savefig(r'Outputs\payments_pie_graphs.png')
            return None

        n = len(monthly_payments_df)
        fig, axes = plt.subplots(1, n, figsize=(4*n, 4))
        
        if n == 1:
            axes = [axes]

        for i, (ax, (_, row)) in  enumerate(zip(axes, monthly_payments_df.iterrows())):
            
            total_pieces = int(row['Number of Payments'])
            colored = int(row['Current Payment Number'])
            grayed_out = total_pieces - colored
            
            
            iteration_color = Local.Colors[i % len(Local.Colors)]

            colors = ["lightgray"] * grayed_out + [iteration_color] * colored 
            
            piece_count = [1] * row['Number of Payments']            

            ax.pie(
                piece_count,
                colors=colors,
                startangle=90,
                counterclock=False,
                wedgeprops={"linewidth": 6, "edgecolor": "white"}  # thick white lines
            )
            ax.set_title(f"{utils.heb_conversion(row['Transaction Name'])}\n", fontsize=12)
        
                # Text *under* the pie chart
            ax.text(
            0.5, -0.05,   # X center, Y a bit below axes
            f"Payment {row['Current Payment']* row['Current Payment Number']:,.2f} / {row['Total Amount']:,.2f} ₪",
            ha="center", va="top", fontsize=10, transform=ax.transAxes
            )

        plt.tight_layout()
        plt.savefig(r'Outputs\payments_pie_graphs.png')
        plt.close()

    @staticmethod
    def plot_monthly_cash_distribution(df_monthly_cash_transactions: pd.DataFrame) -> Tuple[float, float]:
        """
        Plot a pie graph according to the following guidelines:

        In the center, the value of the accumulative cash value of the month will be displayed.
        The pie chart is divided into two main sections: earnings in cash and spendings in cash of the given month,
        the transactions are provided by the df_monthly_cash_transactions data frame and are already filtered to include a single month.
        The pie chart will be displayed in the same UI as the other pie charts (spendings/earnings/investments).
        The pie chart will include spending transactions in red color and earnings transactions in green color.
        2 charts will be generated and saved to the output folder:
            1. A chart grouped by spending/earning and category, displaying the summed value.
            2. A chart grouped by spending/earning and category, displaying the category name.

        Amount spent in cash and the amount earned in cash in the given month will be returned.
        """
        chart_name = "Cash_Distribution"
        chart_title = chart_name.replace('_', ' ')
        
        if df_monthly_cash_transactions.empty:
            Graphics._create_empty_chart(chart_title)
            return 0.0, 0.0

        df = df_monthly_cash_transactions.copy()
        monthly_accumulative = df['Amount'].sum()

        # Separate spendings and earnings
        spendings_df = df[df['Amount'] < 0]
        earnings_df = df[df['Amount'] > 0]

        total_spendings = spendings_df['Amount'].sum() if not spendings_df.empty else 0.0
        total_earnings = earnings_df['Amount'].sum() if not earnings_df.empty else 0.0

        # Add a column to identify if the transaction is a spending or an earning
        df['Type'] = df['Amount'].apply(lambda x: 'Spendings' if x < 0 else 'Earnings')
        df['Amount'] = df['Amount'].abs()
        df = df.groupby(['Type', 'Category'], as_index=False).sum(numeric_only=True)
        # utils.log(f"Cash transactions for the month:\n{utils.df_to_markdown(df)}", 'system')

        DONUT_HOLE_SIZE = 0.70
        FIG_SIZE = (7, 5)
        COLORS = {
            'Spendings': "#f66b85",
            'Earnings': "#4fba89"
        }

        def plot_pie_chart(data: pd.DataFrame, data_index, output_path: str):
            """
            Arg data:
                column Type: 'Spendings' or 'Earnings' to decide on the color
                column Category: category name for indexing the values shown
                column Amount: the value to be shown in the pie chart
            Arg data_index:
                lambda receiving a dataframe row and returning the index value for the pie chart
            Arg output_path:
                path to save the pie chart to

            The function saves a single donut plot to the given output path.
            """
            plot_df = data.copy()
            plot_df = plot_df.set_index(plot_df.apply(data_index, axis=1))
            ax = plot_df.plot.pie(
                y='Amount',
                figsize=FIG_SIZE,
                legend=False,
                title=chart_title,
                colors=[COLORS[t] for t in plot_df['Type']]
            )
            # Donut hole
            my_circle = plt.Circle((0, 0), DONUT_HOLE_SIZE, fc='white')
            plt.gcf().gca().add_artist(my_circle)
            # Center text
            ax.text(0, 0, f"{monthly_accumulative:,.2f} ₪",
                    horizontalalignment='center',
                    verticalalignment='center',
                    fontsize=22,
                    fontweight='bold',
                    color='black',
                    fontname='Arial')
            ax.set_title(chart_title, fontsize=20)
            ax.set_ylabel('')
            plt.savefig(output_path)
            plt.close()

        # Chart 1: Grouped by category name
        plot_pie_chart(data=df,
                       data_index=lambda row: utils.heb_conversion(row['Category']),
                       output_path=f'Outputs\\{chart_name}_category.png')
        
        # Chart 2: Grouped by price
        plot_pie_chart(data=df, 
                       data_index=lambda row: f"{row['Amount']:,.2f}₪",
                       output_path=f'Outputs\\{chart_name}_prices.png')

        return abs(total_spendings), total_earnings

    # ── Mortgage analysis plots ────────────────────────────────────────────────

    @staticmethod
    def _heb(s: str) -> str:
        """
        Reverse a Hebrew string so matplotlib's LTR renderer displays it correctly.
        For mixed lines (Hebrew + number on same line) pass them separately.
        """
        import re
        # Split into Hebrew-only segments and number/punctuation segments,
        # reverse each Hebrew segment, then reverse the order of all segments.
        parts  = re.split(r'(\d[\d,\.]*|[₪—\-]+)', s)
        result = [p[::-1] if not re.match(r'[\d₪—\-,\.]+', p) else p for p in parts]
        return ''.join(reversed(result))

    @staticmethod
    def plot_mortgage_balance(monthly_totals, per_track, today) -> None:
        """
        Line chart: remaining balance over 30 years, per track + total.
        Vertical dashed line marks today.
        Saved → Outputs/Mortgage_Balance.png
        """
        import pandas as pd
        _h = Graphics._heb
        sns.set(style="whitegrid")
        fig, ax = plt.subplots(figsize=(14, 6))

        TRACK_COLORS = {"fixed": "#1e9d8b", "variable": "#f0b429", "prime": "#5b8dee"}
        TRACK_DASH   = {"fixed": "-",        "variable": "--",       "prime": ":"}

        for track_name, group in per_track.groupby("track"):
            ttype = group["track_type"].iloc[0]
            dates = pd.to_datetime(group["month"])
            ax.plot(dates, group["balance"],
                    color=TRACK_COLORS.get(ttype, "#aaa"),
                    linestyle=TRACK_DASH.get(ttype, "-"),
                    linewidth=1.3, alpha=0.55, label=_h(track_name))

        months = pd.to_datetime(monthly_totals["month"])
        ax.plot(months, monthly_totals["total_balance"],
                color="#1a3a5c", linewidth=2.6, label=_h("סה״כ"), zorder=5)

        today_ts = pd.Timestamp(today)
        if months.min() <= today_ts <= months.max():
            mask    = monthly_totals["month"].apply(lambda d: pd.Timestamp(d)) <= today_ts
            cur_bal = monthly_totals[mask]["total_balance"].iloc[-1]

            # Shade historical (paid) region with a very light teal wash
            ax.axvspan(months.min(), today_ts, alpha=0.06, color="#1e9d8b", zorder=0)

            # Gentle gradient boundary line between past and future
            ax.axvline(today_ts, color="#1e9d8b", linewidth=2, linestyle="--",
                       alpha=0.55, zorder=4)

            # "Today" annotation
            ax.annotate(
                f"{_h('היום')}\n₪{cur_bal:,.0f}",
                xy=(today_ts, cur_bal),
                xytext=(44, 18), textcoords="offset points",
                fontsize=9, fontweight="bold", color="#1e9d8b",
                arrowprops=dict(arrowstyle="->", color="#1e9d8b", lw=1.2),
            )

            # Small "paid / projected" labels along the x-axis
            mid_past   = months.min() + (today_ts - months.min()) / 2
            mid_future = today_ts     + (months.max() - today_ts) / 2
            ax.text(mid_past,   ax.get_ylim()[0], _h("בפועל"),    ha="center",
                    va="bottom", fontsize=7.5, color="#1e9d8b", alpha=0.7)
            ax.text(mid_future, ax.get_ylim()[0], _h("תחזית"),    ha="center",
                    va="bottom", fontsize=7.5, color="#888",     alpha=0.7)

        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"₪{v/1000:.0f}K"))
        ax.set_title(_h("יתרת משכנתא לאורך הזמן"), fontsize=16, pad=16)
        ax.set_xlabel(_h("שנה"))
        ax.set_ylabel(_h("יתרה"))
        ax.legend(loc="upper right", fontsize=8)
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(r"Outputs\Mortgage_Balance.png", dpi=120)
        plt.close()

    @staticmethod
    def plot_mortgage_breakdown(monthly_totals) -> None:
        """
        Stacked area: principal vs interest portion of monthly payment over time.
        Saved → Outputs/Mortgage_Breakdown.png
        """
        import pandas as pd
        _h = Graphics._heb
        sns.set(style="whitegrid")
        fig, ax = plt.subplots(figsize=(14, 5))

        months = pd.to_datetime(monthly_totals["month"])
        ax.stackplot(
            months,
            monthly_totals["total_interest"],
            monthly_totals["total_principal"],
            labels=[_h("ריבית"), _h("קרן")],
            colors=["#f66b85", "#1e9d8b"],
            alpha=0.78,
        )

        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"₪{v:,.0f}"))
        ax.set_title(_h("פירוט תשלום חודשי — קרן וריבית"), fontsize=16, pad=15)
        ax.set_xlabel(_h("שנה"))
        ax.set_ylabel(_h("תשלום (₪)"))
        ax.legend(loc="upper right")
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.savefig(r"Outputs\Mortgage_Breakdown.png", dpi=120)
        plt.close()

    @staticmethod
    def plot_mortgage_cashflow(actual_pay_df, actual_rent_df,
                               default_rental: float, projected_payment: float,
                               mortgage_start=None) -> None:
        """
        Grouped bar chart: actual mortgage payment vs actual rental income per month.
        Months with DB data use real values; future months use projected figures.
        Months before mortgage_start show 0 for payment (pre-mortgage period).
        Saved → Outputs/Mortgage_Cashflow.png

        actual_pay_df    – DataFrame [month (date), total_paid]   mortgage payments
        actual_rent_df   – DataFrame [month (date), total_income]  rental receipts
        default_rental   – fallback rent when no DB record (₪)
        projected_payment – fallback mortgage when no DB record (₪)
        mortgage_start   – date of first mortgage payment (months before this → payment=0)
        """
        import pandas as pd
        from datetime import date
        from dateutil.relativedelta import relativedelta

        pay_map  = {} if actual_pay_df.empty  else dict(zip(actual_pay_df["month"],  actual_pay_df["total_paid"]))
        rent_map = {} if actual_rent_df.empty else dict(zip(actual_rent_df["month"], actual_rent_df["total_income"]))

        all_actual_months = sorted(set(list(pay_map.keys()) + list(rent_map.keys())))
        proj_start = (max(all_actual_months) + relativedelta(months=1)) if all_actual_months else date.today().replace(day=1)

        rows = []
        for m in all_actual_months:
            # Before mortgage started: no payment yet, don't flag as missing
            before_mortgage = mortgage_start is not None and m < mortgage_start
            if before_mortgage:
                pay_val = 0.0
                pay_src = "pre-mortgage"
            elif m in pay_map:
                pay_val = pay_map[m]
                pay_src = "actual"
            else:
                pay_val = projected_payment
                pay_src = "projected"
            rows.append({
                "month":   m,
                "payment": pay_val,
                "rental":  rent_map.get(m, 0),
                "pay_src": pay_src,
                "rnt_src": "actual" if m in rent_map else "missing",
            })
        for i in range(6):
            m = proj_start + relativedelta(months=i)
            rows.append({"month": m, "payment": projected_payment,
                         "rental": default_rental, "pay_src": "projected", "rnt_src": "projected"})

        df = pd.DataFrame(rows).sort_values("month").reset_index(drop=True)

        _h     = Graphics._heb
        labels = [r["month"].strftime("%m/%y") for _, r in df.iterrows()]
        pays   = df["payment"].tolist()
        rents  = df["rental"].tolist()
        nets   = [p - r for p, r in zip(pays, rents)]
        pay_colors  = ["#e74c3c" if k == "actual" else "#f08080" if k == "projected" else "#cccccc" for k in df["pay_src"]]
        rent_colors = ["#1e9d8b" if k == "actual" else "#6fcfba"
                       if k == "projected" else "#e74c3c" for k in df["rnt_src"]]

        x     = np.arange(len(labels))
        width = 0.38

        sns.set(style="whitegrid")
        fig, ax = plt.subplots(figsize=(14, 5))

        ax.bar(x - width / 2, pays,  width, color=pay_colors,  zorder=3)
        ax.bar(x + width / 2, rents, width, color=rent_colors,  zorder=3)
        ax.plot(x, nets, color="#f0b429", linewidth=2, marker="o", markersize=5, zorder=4)

        # Mark months where rent is missing with a red ✗
        for i, row in df.iterrows():
            if row["rnt_src"] == "missing":
                ax.text(i + width / 2, 80, "X", ha="center", va="bottom",
                        color="#e74c3c", fontsize=11, fontweight="bold", zorder=5)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"₪{v:,.0f}"))
        ax.set_title(_h("תשלום משכנתא מול הכנסת שכירות (בפועל + תחזית)"), fontsize=14, pad=14)
        ax.set_ylabel("₪")

        import matplotlib.patches as mpatches
        handles = [
            mpatches.Patch(color="#e74c3c", label=_h("משכנתא בפועל")),
            mpatches.Patch(color="#f08080", label=_h("משכנתא משוערת")),
            mpatches.Patch(color="#1e9d8b", label=_h("שכירות בפועל")),
            mpatches.Patch(color="#6fcfba", label=_h("שכירות משוערת")),
            plt.Line2D([0], [0], color="#f0b429", lw=2, label=_h("עלות נטו")),
        ]
        ax.legend(handles=handles, loc="upper right", fontsize=8)

        plt.tight_layout()
        plt.savefig(r"Outputs\Mortgage_Cashflow.png", dpi=120)
        plt.close()

    @staticmethod
    def plot_housing_pie(alltime_out: float, alltime_income: float,
                         initial_payment: float = 0) -> None:
        """
        Donut pie with 3 slices:
          1. Initial apartment purchase payments (100k + 100k + 28,040)
          2. Ongoing spending (mortgage payments, fees, etc.)
          3. Total rental income received
        Saved → Outputs/Mortgage_Pie.png
        """
        _h = Graphics._heb
        ongoing_out = max(alltime_out - initial_payment, 0)

        values  = [initial_payment, ongoing_out, alltime_income]
        labels  = [_h("תשלום ראשוני לרכישה"), _h("הוצאות שוטפות"), _h("הכנסות שכירות")]
        colors  = ["#1e9d8b", "#f66b85", "#27ae60"]
        explode = (0.06, 0.03, 0.03)

        fig, ax = plt.subplots(figsize=(7, 5))
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, colors=colors, explode=explode,
            autopct=lambda p: f"₪{p/100*sum(values):,.0f}\n({p:.1f}%)",
            startangle=120,
            wedgeprops=dict(width=0.58, edgecolor="white", linewidth=2),
            textprops=dict(fontsize=9),
        )
        for at in autotexts:
            at.set_fontsize(8.5)
            at.set_fontweight("bold")
            at.set_color("white")

        net = alltime_out - alltime_income
        ax.text(0, 0, f"₪{net:,.0f}\n{_h('הפרש נטו')}",
                ha="center", va="center", fontsize=9, fontweight="bold", color="#1a3a5c")

        ax.set_title(_h("הוצאות מול הכנסות — כל הזמנים"), fontsize=13, pad=14)
        plt.tight_layout()
        plt.savefig(r"Outputs\Mortgage_Pie.png", dpi=120)
        plt.close()
