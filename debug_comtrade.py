"""
Run this once to see exactly what UN Comtrade's preview endpoint returns.
Paste the output back so we can find why the monthly total came back
~6x higher than Germany's real monthly average (~100,000 tons).
"""

import comtradeapicall

df = comtradeapicall.previewFinalData(
    typeCode="C", freqCode="M", clCode="HS", period="202508",
    reporterCode="276", cmdCode="0901", flowCode="M",
    partnerCode=None, partner2Code=None, customsCode=None,
    motCode=None, includeDesc=True,
)

print("Number of rows returned:", len(df))
print("\nColumns:", list(df.columns))
print("\nUnique period values:", df["period"].unique() if "period" in df.columns else "no 'period' column")
print("\nUnique partnerDesc values:", df["partnerDesc"].unique() if "partnerDesc" in df.columns else "no 'partnerDesc' column")
print("\nnetWgt sum:", df["netWgt"].sum() if "netWgt" in df.columns else "no 'netWgt' column")
print("\nFirst 10 rows (netWgt, period, partnerDesc, reporterDesc):")
cols_to_show = [c for c in ["period", "reporterDesc", "partnerDesc", "netWgt", "cmdCode"] if c in df.columns]
print(df[cols_to_show].head(10).to_string())
