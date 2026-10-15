# Viswa Finance

A personal finance tracker that runs entirely in the browser. It has no build step and no dependencies, and your data never leaves your device.

## Features

- Add, edit and delete income and expense transactions with a category, a date and a note
- Summary cards for all-time balance, this month's income and expenses (with the change from last month) and savings rate
- Spending-by-category donut chart and a six-month income vs. expenses chart
- Monthly budgets per category, with progress bars that turn amber at 80% and red when over
- Search and filter by type, and browse any month
- Currencies: INR, USD, EUR, GBP and JPY
- Export to CSV, back up and restore as JSON, and load sample data
- Light and dark mode, and a layout that works on phones

## Run it

Open `index.html` in a browser, or serve the folder:

```sh
python3 -m http.server 8000
# then visit http://localhost:8000
```

Data is saved in the browser's `localStorage`. Use **Backup JSON** to move it to another browser or device.
