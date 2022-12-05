
## Purpose

It pulls data from W1000 portal reports.

## Changelog

  - 2022-12-05: implementing +A/-A data as statistics - huge thanks to [wrobi](https://github.com/wrobi) for making it! Please note, you need add curve `A` to your report (see the screenshots below)   
  - 2022-12-01: hotfix #9: restricting data polls to morning hours and HA reboots
  - 2022-11-22: fixed bug that occured when report name list included space in configuration.yaml

## Usage

### Prepare data sources

1. Register and log in to your provider's portal (e.g. https://energia.eon-hungaria.hu/W1000 in Hungary)
2. Create a new Workarea, if you don't have yet
3. Add a report to your workarea. Remember this report name, it will be your new sensor in Home Assistant: ![screenshots](https://user-images.githubusercontent.com/4962619/205730258-69a2c878-bf2a-485c-aef5-094c36f25ed6.png)

4. Do you have solar production (export)? Create a new, similar report with curves **DP_1-1:2.8.0** and **-A**.

### Set up Home Assistant

In `configuration.yaml`, give the integration your login details:

```
w1000-energy-monitor:
  login_user: !secret w1000-email-address
  login_pass: !secret w1000-password
  url: https://energia.eon-hungaria.hu/W1000
  reports: import,export
```

_(report names are case-sensitive)_

#### Energy Dashboard

The new sensors are ready to be added to the Energy Dashboard. Please note, the graph for the current day can be messy as the latest data is not consistent.

### Further info

Have some problems? Looking for examples? Visit the
[Wiki](https://github.com/ZsBT/hass-w1000-portal/wiki).

### Contribute!

If you find this integration useful and think you're good in programming,
feel free to create pull requests. I'd be thankful for code reviews,
security audits.

I am open to
[discuss](https://github.com/ZsBT/hass-w1000-portal/discussions) new ideas,
change considerations.

