# BNP Wealth Management — additional ISIN/date closing prices

Queried via the site search + AJAX endpoint `web-financialinfo-service/api/marketdata/funds?...field=HistoryV1...` page-by-page.

| ISIN | Target date | Resolved BNP URL | Historical URL | Close (LAST) | Currency | Exchange | Consors ID | Page |
|---|---|---|---|---:|---|---|---|---:|
| IE000M7V94E1 | 2026-02-04 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Etf/Vaneck_Uranium_And_Nuclear_Technologies-IE000M7V94E1 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Etf/Vaneck_Uranium_And_Nuclear_Technologies-IE000M7V94E1/Kurse-und-Handelsplaetze/Historische-Kurse | 53.86 | EUR | GAT (Tradegate BSX) | _413905979 | 0 |
| IE00BP3QZB59 | 2026-02-04 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Etf/Ishares_Edge_Msci_World_Value_Factor_Uci-IE00BP3QZB59 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Etf/Ishares_Edge_Msci_World_Value_Factor_Uci-IE00BP3QZB59/Kurse-und-Handelsplaetze/Historische-Kurse | 55.36 | EUR | GAT (Tradegate BSX) | _142442269 | 0 |
| GB0009390070 | 2026-01-06 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Aktie/Volex_Plc-GB0009390070 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Aktie/Volex_Plc-GB0009390070/Kurse-und-Handelsplaetze/Historische-Kurse | 4.94 | EUR | GAT (Tradegate BSX) | _358704103 | 0 |
| IE00BMW42306 | 2025-06-13 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Etf/Ishares_Msci_Europe_Financials_Sector_Uc-IE00BMW42306 | https://www.wealthmanagement.bnpparibas.de/web/Wertpapier/Etf/Ishares_Msci_Europe_Financials_Sector_Uc-IE00BMW42306/Kurse-und-Handelsplaetze/Historische-Kurse | 12.02 | EUR | GAT (Tradegate BSX) | _369597456 | 3 |

Notes:
- Pagination is zero-based (`page=3` means 4th page).
- Values are the `LAST` field for the requested date.
