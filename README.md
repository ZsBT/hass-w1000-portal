
## Purpose

It pulls data from W1000 portal reports.
See some screenshots at the Wiki page.

## Prepare data sources

Register and log in to your provider's portal (e.g. https://energia.eon-hungaria.hu/W1000 in Hungary)
Create a new Workarea (use any name)
Add a report to your workarea. Remember this report name, it will be your new sensor in Home Assistant.
Add exactly one curve (e.g. HU0XXXXX-1:1.8.0*0 is the total power consumption counter of your electricity meter) to your report. I recommend setting a 3-day interval.

You can create more reports on any workareas, just make sure you have exactly one curve at a report.

