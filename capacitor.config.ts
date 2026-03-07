import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'au.com.teslafsd.finder',
  appName: 'Tesla FSD Finder',
  webDir: 'static',
  // Point API calls to the Railway backend
  server: {
    // Replace with your actual Railway deployment URL
    url: 'https://tesla-fsd-finder-au.up.railway.app',
    cleartext: false,
    // Allow navigation to external listing sites
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
      spinnerColor: '#3b82f6',
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
  }
};

export default config;
