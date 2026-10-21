"""Builds a workbook laid out like a Screener.in 'Export to Excel' file (values only, ₹ crores)."""

import datetime as dt
import io

from openpyxl import Workbook

YEARS = [dt.datetime(y, 3, 31) for y in (2021, 2022, 2023, 2024, 2025)]


def screener_bytes() -> bytes:
    wb = Workbook()
    pl = wb.active
    pl.title = "Profit & Loss"
    pl["A1"] = "Narration"
    pl["B2"] = "='Data Sheet'!B17"  # formula sheets with no saved results, like the real export
    ds = wb.create_sheet("Data Sheet")
    rows = [
        ["COMPANY NAME", "TATA CONSULTANCY SERVICES LTD"],
        ["LATEST VERSION", 2.1],
        [], ["META"], ["Number of shares", 361.81], ["Face Value", 1], ["Current Price", 3050], ["Market Capitalization", 1103521],
        [], [], [], [], [], [],
        ["PROFIT & LOSS"],
        ["Report Date", *YEARS],
        ["Sales", 164177, 191754, 225458, 240893, 255324],
        ["Raw Material Cost", 0, 0, 0, 0, 0],
        ["Change in Inventory", 0, 0, 0, 0, 0],
        ["Power and Fuel", 0, 0, 0, 0, 0],
        ["Other Mfr. Exp", 33000, 40000, 45000, 46000, 48000],
        ["Employee Cost", 91417, 107554, 127522, 140131, 149000],
        ["Selling and admin", 6000, 7000, 8000, 8500, 9000],
        ["Other Expenses", 1500, 1700, 2000, 2200, 2400],
        ["Other Income", 4228, 4018, 3449, 4422, 3962],
        ["Depreciation", 4065, 4604, 5022, 4985, 5242],
        ["Interest", 637, 784, 779, 778, 796],
        ["Profit before tax", 42437, 51787, 56807, 62180, 64648],
        ["Tax", 9801, 13238, 14604, 15898, 16534],
        ["Net profit", 32430, 38327, 42147, 46099, 48553],
        ["Dividend Amount", 14000, 15500, 42000, 26000, 45000],
        [],
        ["Quarters"],
        ["Report Date", dt.datetime(2024, 6, 30), dt.datetime(2024, 9, 30), dt.datetime(2024, 12, 31), dt.datetime(2025, 3, 31)],
        ["Sales", 62613, 64259, 63973, 64479],
        ["Net profit", 12105, 11955, 12444, 12293],
        [],
        ["BALANCE SHEET"],
        ["Report Date", *YEARS],
        ["Equity Share Capital", 370, 366, 366, 362, 362],
        ["Reserves", 86063, 88773, 90058, 90127, 94394],
        ["Borrowings", 7795, 7818, 7688, 8021, 9392],
        ["Other Liabilities", 35624, 44115, 44880, 46185, 47872],
        ["Total", 129852, 141072, 142992, 144695, 152020],
        ["Net Block", 18833, 18975, 18882, 18961, 20000],
        ["Capital Work in Progress", 920, 963, 1234, 1564, 1500],
        ["Investments", 29330, 30485, 37163, 31762, 30000],
        ["Other Assets", 80769, 90649, 85713, 92408, 100520],
        ["Total", 129852, 141072, 142992, 144695, 152020],
        ["Receivables", 30079, 36764, 41257, 41693, 45000],
        ["Inventory", 8, 28, 28, 28, 30],
        ["Cash & Bank", 9329, 12488, 11032, 9016, 10000],
        ["No. of Equity Shares", 3699051373, 3657051373, 3659051373, 3618087518, 3618087518],
        [],
        ["CASH FLOW:"],
        ["Report Date", *YEARS],
        ["Cash from Operating Activity", 38802, 39949, 41965, 44338, 48908],
        ["Cash from Investing Activity", -7956, 897, -3164, 5998, -3000],
        ["Cash from Financing Activity", -32634, -33581, -47878, -48536, -44000],
        ["Net Cash Flow", -1788, 7265, -9077, 1800, 1908],
        [],
        ["PRICE:", 3150, 3740, 3210, 3880, 3600],
        [],
        ["DERIVED:"],
        ["Adjusted Equity Shares in Cr", 369.9, 365.7, 365.9, 361.8, 361.8],
    ]
    for r in rows:
        ds.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
