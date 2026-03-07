# iOS App Store Deployment Guide

Complete guide to building and deploying Tesla FSD Finder to the Apple App Store.

---

## Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| macOS | Ventura 13.0+ | Required for Xcode |
| Xcode | 15.0+ | Download from Mac App Store |
| Node.js | 18.0+ | `brew install node` |
| CocoaPods | 1.14+ | `sudo gem install cocoapods` |
| Apple Developer Account | $99/year | [developer.apple.com](https://developer.apple.com) |

## 1. Initial Setup

```bash
# Clone the repo
git clone https://github.com/beetrootblues/tesla-fsd-finder-au.git
cd tesla-fsd-finder-au

# Run the build script
chmod +x scripts/build-ios.sh
./scripts/build-ios.sh --open
```

This installs dependencies, syncs the web app to the native iOS project, and opens Xcode.

## 2. Xcode Configuration

### Signing & Capabilities
1. Open `ios/App/App.xcworkspace` in Xcode
2. Select the **App** target in the project navigator
3. Go to **Signing & Capabilities** tab
4. Select your **Team** from the dropdown
5. Ensure **Bundle Identifier** is `au.com.teslafsd.finder`
6. Xcode will auto-create the provisioning profile

### Required Capabilities
These should already be configured, but verify:
- **Push Notifications** (for price drop alerts)
- **Background Modes** > Remote notifications
- **Associated Domains** (if adding universal links later)

### App Icons
1. Place your 1024x1024 `icon.png` in the `assets/` directory
2. Run `npm run icons` to generate all required sizes
3. Or manually add icons in Xcode: Assets.xcassets > AppIcon

## 3. Testing

### Simulator
```bash
# Build and run on simulator
npx cap run ios
```

### Physical Device
1. Connect your iPhone via USB
2. In Xcode, select your device from the destination dropdown
3. Press Cmd+R to build and run
4. First run: trust the developer certificate on your device
   (Settings > General > VPN & Device Management)

### TestFlight (Beta Testing)
1. In Xcode: **Product > Archive**
2. In the Archives organizer: **Distribute App**
3. Select **App Store Connect** > **Upload**
4. Go to [App Store Connect](https://appstoreconnect.apple.com)
5. Select your app > TestFlight tab
6. Add internal/external testers

## 4. App Store Submission

### App Store Connect Setup
1. Go to [App Store Connect](https://appstoreconnect.apple.com)
2. Click **+** > **New App**
3. Fill in:
   - **Platform**: iOS
   - **Name**: Tesla FSD Finder
   - **Primary Language**: English (Australia)
   - **Bundle ID**: au.com.teslafsd.finder
   - **SKU**: tesla-fsd-finder-au

### App Store Listing

**Category**: Utilities (primary), Lifestyle (secondary)

**Description** (suggested):
```
Find underpriced Teslas with Full Self-Driving (FSD) and Enhanced Autopilot (EAP) across Australia's major car marketplaces.

Tesla FSD Finder automatically scans 7 Australian car listing sites every 6 hours and highlights vehicles where sellers haven't priced in the value of FSD or EAP - features worth $5,000 to $15,000+.

FEATURES:
- Search across Carsales, Drive, AutoTrader, Gumtree, CarsGuide, Pickles, and Facebook Marketplace
- FSD confidence scoring with keyword analysis
- Price drop tracking and alerts
- Side-by-side listing comparison
- Save listings to your watchlist
- Interactive map view of all listings
- Dark and light theme
- Push notifications for price drops

IMPORTANT: FSD transferability policy changes on March 31. Vehicles purchased before this date may retain lifetime FSD transfers. After this date, FSD becomes subscription-only for new owners.
```

**Keywords**: tesla, fsd, full self driving, autopilot, used cars, australia, electric vehicle, ev, carsales, price tracker

**Privacy Policy URL**: Host a simple privacy policy page (required for push notifications)

### Screenshots
Required sizes:
- iPhone 6.7" (1290 x 2796) - iPhone 15 Pro Max
- iPhone 6.5" (1284 x 2778) - iPhone 14 Plus
- iPad Pro 12.9" (2048 x 2732) - if supporting iPad

Take screenshots in Xcode Simulator:
```bash
# Run on specific simulator
xcrun simctl boot "iPhone 15 Pro Max"
npx cap run ios --target "iPhone 15 Pro Max"
# Then Cmd+S in the simulator to capture
```

### Review Guidelines Compliance

This app is designed to pass **Guideline 4.2** (Minimum Functionality) by providing:

1. **Native push notifications** - Real-time price drop alerts via APNs
2. **Biometric authentication** - Face ID / Touch ID lock
3. **Native share sheet** - iOS share extension for listings
4. **Haptic feedback** - Tactile responses on interactions
5. **Offline support** - Cached watchlist available without connectivity
6. **Network monitoring** - Native connectivity detection
7. **App badge** - Unread alert count on home screen icon

### Submit for Review
1. Archive in Xcode: **Product > Archive**
2. Upload to App Store Connect
3. Fill in all metadata, screenshots, and privacy details
4. Click **Submit for Review**
5. Typical review time: 24-48 hours

## 5. Post-Launch

### Push Notification Setup (APNs)
To actually send push notifications, you'll need:

1. **APNs Key** from Apple Developer Portal:
   - Go to Certificates, Identifiers & Profiles > Keys
   - Create a new key with Apple Push Notifications service (APNs)
   - Download the .p8 file (save it securely)

2. **Server-side sending**: Add a push notification service (e.g., Firebase Cloud Messaging, OneSignal, or direct APNs) to your Railway backend that reads from `/data/devices.json` and sends to registered tokens.

### Updating the App
```bash
# After making changes to the web frontend:
npx cap sync ios

# Open Xcode, bump version number, archive, and upload
npx cap open ios
```

### Environment Variables
Set your Railway backend URL in `capacitor.config.ts`:
```typescript
server: {
  url: 'https://your-app.up.railway.app',
}
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Pod install fails | `cd ios/App && pod repo update && pod install` |
| Signing errors | Ensure Apple Developer membership is active and team is selected |
| Push not working | Check APNs key is configured and device token is registered |
| White screen on launch | Verify `webDir` in capacitor.config.ts points to `static` |
| Build fails on M1/M2 | Run Xcode with Rosetta or update CocoaPods: `arch -x86_64 pod install` |
