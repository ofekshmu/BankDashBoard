import matplotlib
matplotlib.use('Agg')  # non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils
import seaborn as sns
from Constants import GENERAL_PLOT
from Constants import Local
from typing import Tuple
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime
import os

_OUTPUTS_DIR = '/tmp/Outputs' if os.getenv('DATABASE_URL') else 'Outputs'
os.makedirs(_OUTPUTS_DIR, exist_ok=True)


def _out(filename: str) -> str:
    """Return a writable output path for a chart file."""
    return os.path.join(_OUTPUTS_DIR, filename)


class Graphics:

    @staticmethod
    def plot_general(spendings: list,
                     spendings_overall: list,
                     earnings: list,
                     topic: str = "",
                     title_ext: str = "",
                     lp_Overall_income: bool = True,
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

        sns.barplot(x="Months", y="Amount", hue="Category",
                    data=data["invest_df"][::-1], ax=ax,
                    palette=[COLORS['earnings'], COLORS['investments']])

        if lp_Overall_income:
            sns.lineplot(x="Months", y="Overall Income",
                        data=data["overall_df"], ax=ax,
                        color=COLORS['net_income'],
                        marker='o', linestyle='--')
            add_value_annotations(ax, data["overall_df"], COLORS['net_income'])

        # Styling
        ax.legend(handles=create_legend_handles())
        ax.set_xlabel("Months", fontsize=FONT_SIZES['labels'])
        ax.set_ylabel("Amount (₪)", fontsize=FONT_SIZES['labels'])
        ax.set_title(f"Monthly Spendings and Earnings {title_ext}", fontsize=FONT_SIZES['title'])
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, tick_number: f'{value:,.0f}₪' ))

        # Save plot
        output_path = _out(f'General_info{"_" + title_ext if title_ext else ""}.png')
        plt.savefig(output_path, bbox_inches='tight')
        plt.close()

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

        plt.savefig(_out('Category_Distribution.png'))
        return outliers_lst
