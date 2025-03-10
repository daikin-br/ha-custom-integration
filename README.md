The **Daikin Smart AC** integration enables Home Assistant to control Daikin smart air conditioning systems.

## Supported hardware

This Home Assistant integration supports the Brazilian version of Daikin Smart AC products, which are operated by **Daikin Smart AC** mobile apps available on the following mobile platforms:

- [iOS](https://apps.apple.com/br/app/daikin-smart-ac/id1557849398)

- [Android](https://play.google.com/store/apps/details?id=in.co.iotalabs.dmb.smartac)
  

## Prerequisites
  
- The Daikin air conditioning device must already be added to your account using the Daikin Smart AC mobile app.

- The integration requires a **Device Key**. To retrieve the Device Key for the SSID (shown in the Home Assistant configuration UI during setup), open the Daikin Smart AC mobile app, navigate to **Menu -> Integrations -> Home Assistant**, enter or select the SSID, and press **Submit**.

## Installation

1. Download it with HACS
2. Restart Home Assistant
3. In the HA UI:
    - Go to "Settings" -> "Devices & Services" -> "Integrations",  click "+" and search for "**Daikin Smart AC**"
4. If "**Daikin Smart AC**" is not available then ADD it manually as shown below:

![Add Repository](images/ha-custom-repo-setup-1.png "Add Repository")
![Add Repository](images/ha-custom-repo-setup-2.png "Add Repository")


## Configuration

To add the **Daikin Smart AC** integration to your Home Assistant instance, use the following My button:

[![Open your Home Assistant instance and show an integration.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=daikin_br)

Daikin Smart AC can be **auto-discovered** by Home Assistant. If an instance was found, it will be shown as **Discovered Device: DAIKINXXXXXX**. You can then click on `ADD` and follow the on screen instructions to set it up.

If it wasn’t discovered automatically, You can set up a manual integration entry:
- Browse to your Home Assistant instance.
- Go to Settings -> Devices & Services.
- In the bottom right corner, select the Add Integration button.
- From the list, select Daikin Smart AC.
- Follow the instructions on screen to complete the setup.

### Note:

If your Daikin Smart AC unit is not on the same network as your Home Assistant instance (e.g., if your network is segmented), **automatic device discovery** may not work. In this case, you will need to manually find the Device IP by:

- Accessing your network router’s setup page and locating the client IP for the Daikin Smart AC device (hostname format: DAIKINXXXXXX).

**To configure the device, ensure the following ports are accessible:**

- From Home Assistant to the Daikin Smart AC Device : `TCP Port` => `15914`

- Default mDNS port.

If this applies to your setup, adjust your firewall settings to allow access to the required ports.

## Climate

The `daikin_br` climate platform integrates Daikin air conditioning systems with Home Assistant, allowing control over the following parameters:

- [**HVAC Mode**](https://www.home-assistant.io/integrations/climate/#action-climateset_hvac_mode) (`off`, `heat`, `cool`, `dry`, `fan_only`)

- [**Target Temperature**](https://www.home-assistant.io/integrations/climate#action-climateset_temperature)

- [**Fan Mode**](https://www.home-assistant.io/integrations/climate#action-climateset_fan_mode) (fan speed)

- [**Swing Mode**](https://www.home-assistant.io/integrations/climate#action-climateset_swing_mode)

- [**Preset Mode**](https://www.home-assistant.io/integrations/climate#action-climateset_preset_mode) (eco, boost)

Current ambient temperature is also displayed.

## Known limitations

There are no known limitations for this integration.

## Troubleshooting

There are no commonly known issues with this integration.

## Removing the integration

This integration follows standard integration removal. No extra steps are required.
1. In Home Assistant, go to [**Setting->Device & Services**](https://my.home-assistant.io/redirect/integrations/).
2. Select the **Daikin Smart AC** integration and in the three-dot menu (:material-dots-vertical:), select **Delete**.
3. [Restart Home Assistant](https://www.home-assistant.io/docs/configuration/#reloading-the-configuration-to-apply-changes).

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

***
