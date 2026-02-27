# Green Mountain Power (GMP)

> ⚠️ This is an unofficial Home Assistant integration for Green Mountain Power.  
> Green Mountain Power and its logo are trademarks of Green Mountain Power.  
> This project is not affiliated with or endorsed by Green Mountain Power.

Home Assistant custom integration for Green Mountain Power usage and EV charging data.

## Installation (HACS)

1. In Home Assistant, go to **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/findthelorax/gmp` as **Integration**
3. Install **Green Mountain Power**
4. Restart Home Assistant
5. Go to **Settings → Devices & services → Add integration** and search for **Green Mountain Power**

## Configuration

- Enter your GMP **username** and **password**.
- The integration will try to auto-discover account IDs.
  - If multiple accounts are found, you can select one.
  - If discovery fails, you can enter the account ID manually.

## Entities

This integration currently provides:

- Energy usage (today total, last hour)
- Account status / power status
- Monthly usage and selected-day totals
- EV charging consumption and cost (when available)
- A select entity to choose which day’s hourly usage to summarize

## Notes

- This is an unofficial integration and is not affiliated with Green Mountain Power.
- Your credentials are stored in Home Assistant’s config entries.

## Support

- Issues: https://github.com/findthelorax/gmp/issues
