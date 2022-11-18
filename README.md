
## Purpose

It pulls data from W1000 portal reports.

## Prepare data sources

1. Register and log in to your provider's portal (e.g. https://energia.eon-hungaria.hu/W1000 in Hungary)
2. Create a new Workarea, if you don't have yet
3. Add a report to your workarea. Remember this report name, it will be your new sensor in Home Assistant.
4. Add exactly one curve (e.g. HU0XXXXX-1:1.8.0*0 is the total power consumption counter of your electricity meter) to your report. I recommend setting a 3-day interval:
![screenshot](https://github.com/ZsBT/hass-w1000-portal/raw/main/screenshot-w1000-workarea.png?raw=true)

5. optional: repeat steps 3-4

You can create more reports on any workareas, just make sure you have exactly one curve at a report.

## Set up Home Assistant

See the [configuration example](https://github.com/ZsBT/hass-w1000-portal/blob/main/configuration-example.yaml) on how to give the integration your login details.

### Energy Dashboard

As the kind of measurement [can not be detected automatically](https://github.com/ZsBT/hass-w1000-portal/issues/1), you need to create a helper (e.g. a template sensor) to make the Energy Dashboard understand it. For example, the total consumption is an increasing value, so this can be added to the dashboard:

```
- template:
    - sensor:
        - name: teljes energiafogyasztás
          unit_of_measurement: "kWh"
          state_class: total_increasing
          device_class: energy
          state: >
            {{ states("sensor.w1000_oraallas") | float }}
```
