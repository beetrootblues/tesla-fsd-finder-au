import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'au.com.teslafsd.finder',
  appName: 'Tesla FSD Finder',
  webDir: 'static',
  // Bundled app mode: the native app ships the web assets inside the binary
  // and reaches the backend through window.API_BASE (see static/config.js).
  // To point the app at your deployed backend, set API_BASE there and
  // re-run `npx cap sync` + rebuild. No server.url needed -- and a hardcoded
  // URL here would silently outlive the deployment it points at.
  server: {
    cleartext: false,
    // Allow the in-app browser / external links to open listing sites.
    allowNavigation: [
      'carsales.com.au',
      'drive.com.au',
      'autotrader.com.au',
      'gumtree.com.au',
      'carsguide.com.au',
      'pickles.com.au',
      'facebook.com'
    ]
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      launchAutoHide: true,
      backgroundColor: '#0a0e1a',
      showSpinner: true,
      spinnerColor: '#e82127',
      splashFullScreen: true,
      splashImmersive: true
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#0a0e1a'
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert']
    },
    Keyboard: {
      resize: 'body',
      style: 'DARK'
    }
  },
  ios: {
    contentInset: 'automatic',
    backgroundColor: '#0a0e1a',
    preferredContentMode: 'mobile',
    scheme: 'Tesla FSD Finder'
  },
  android: {
    backgroundColor: '#0a0e1a'
  }
};

export default config;
