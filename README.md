
## Purpose

It pulls data from W1000 portal reports.
See some screenshots at the Wiki page.

## Prepare data sources

1. Register and log in to your provider's portal (e.g. https://energia.eon-hungaria.hu/W1000 in Hungary)
2. Create a new Workarea (use any name)
3. Add a report to your workarea. Remember this report name, it will be your new sensor in Home Assistant.
4. Add exactly one curve (e.g. HU0XXXXX-1:1.8.0*0 is the total power consumption counter of your electricity meter) to your report. I recommend setting a 3-day interval.
5. optional: repeat steps 3-4

You can create more reports on any workareas, just make sure you have exactly one curve at a report.

## Set up Home Assistant

See the [configuration example](configuration-example.yaml) on how to give the integration your login details.
