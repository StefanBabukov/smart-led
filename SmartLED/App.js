import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  TextInput,
  SafeAreaView,
  StatusBar,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = '@smart_led_ip';
const WS_PORT = 8765;
const RECONNECT_DELAY = 2000;

export default function App() {
  const [ip, setIp] = useState('192.168.1.100');
  const [connected, setConnected] = useState(false);
  const [ledState, setLedState] = useState({
    mode: 'animation',
    effect_name: '',
    effect_index: 0,
    brightness: 255,
    enabled: true,
    total_effects: 20,
  });

  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const intentionalClose = useRef(false);

  // Load saved IP on startup
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      if (saved) setIp(saved);
    });
  }, []);

  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      intentionalClose.current = true;
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const connect = useCallback(() => {
    cleanup();
    intentionalClose.current = false;

    AsyncStorage.setItem(STORAGE_KEY, ip);

    const ws = new WebSocket(`ws://${ip}:${WS_PORT}`);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'state') {
          setLedState(data);
        }
      } catch {}
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      if (!intentionalClose.current) {
        reconnectTimer.current = setTimeout(() => connect(), RECONNECT_DELAY);
      }
    };

    ws.onerror = () => {
      // onclose will fire after this
    };

    wsRef.current = ws;
  }, [ip, cleanup]);

  const disconnect = useCallback(() => {
    cleanup();
  }, [cleanup]);

  const send = useCallback((action) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action }));
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  const brightnessPercent = Math.round((ledState.brightness / 255) * 100);
  const barWidth = `${brightnessPercent}%`;

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#111" />

      {/* Title */}
      <Text style={styles.title}>SMART LED REMOTE</Text>

      {/* Connection */}
      <View style={styles.connectionRow}>
        <TextInput
          style={styles.ipInput}
          value={ip}
          onChangeText={setIp}
          placeholder="Pi IP address"
          placeholderTextColor="#666"
          keyboardType="numeric"
          autoCorrect={false}
        />
        {!connected ? (
          <TouchableOpacity style={styles.connectBtn} onPress={connect}>
            <Text style={styles.connectBtnText}>Connect</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={[styles.connectBtn, styles.disconnectBtn]} onPress={disconnect}>
            <Text style={styles.connectBtnText}>Disconnect</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Status */}
      <View style={styles.statusBox}>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Status</Text>
          <Text style={[styles.statusValue, connected ? styles.statusOn : styles.statusOff]}>
            {connected ? 'Connected' : 'Disconnected'}
          </Text>
        </View>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Mode</Text>
          <Text style={styles.statusValue}>
            {ledState.mode === 'animation' ? 'Animation' : 'Static'}
          </Text>
        </View>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Effect</Text>
          <Text style={styles.statusValue} numberOfLines={1}>
            {ledState.effect_name} ({ledState.effect_index + 1}/{ledState.total_effects})
          </Text>
        </View>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Power</Text>
          <Text style={[styles.statusValue, ledState.enabled ? styles.statusOn : styles.statusOff]}>
            {ledState.enabled ? 'ON' : 'OFF'}
          </Text>
        </View>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Brightness</Text>
          <Text style={styles.statusValue}>{ledState.brightness} ({brightnessPercent}%)</Text>
        </View>
        <View style={styles.brightnessBarBg}>
          <View style={[styles.brightnessBarFg, { width: barWidth }]} />
        </View>
      </View>

      {/* D-Pad Controls */}
      <View style={styles.dpad}>
        <View style={styles.dpadRow}>
          <View style={styles.dpadSpacer} />
          <TouchableOpacity
            style={[styles.dpadBtn, styles.dpadUp]}
            onPress={() => send('up')}
            activeOpacity={0.6}
          >
            <Text style={styles.dpadBtnIcon}>+</Text>
            <Text style={styles.dpadBtnLabel}>BRIGHT</Text>
          </TouchableOpacity>
          <View style={styles.dpadSpacer} />
        </View>
        <View style={styles.dpadRow}>
          <TouchableOpacity
            style={[styles.dpadBtn, styles.dpadLeft]}
            onPress={() => send('previous')}
            activeOpacity={0.6}
          >
            <Text style={styles.dpadBtnIcon}>&larr;</Text>
            <Text style={styles.dpadBtnLabel}>PREV</Text>
          </TouchableOpacity>
          <View style={styles.dpadCenter} />
          <TouchableOpacity
            style={[styles.dpadBtn, styles.dpadRight]}
            onPress={() => send('next')}
            activeOpacity={0.6}
          >
            <Text style={styles.dpadBtnIcon}>&rarr;</Text>
            <Text style={styles.dpadBtnLabel}>NEXT</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.dpadRow}>
          <View style={styles.dpadSpacer} />
          <TouchableOpacity
            style={[styles.dpadBtn, styles.dpadDown]}
            onPress={() => send('down')}
            activeOpacity={0.6}
          >
            <Text style={styles.dpadBtnIcon}>-</Text>
            <Text style={styles.dpadBtnLabel}>BRIGHT</Text>
          </TouchableOpacity>
          <View style={styles.dpadSpacer} />
        </View>
      </View>

      {/* Mode Buttons */}
      <View style={styles.modeRow}>
        <TouchableOpacity
          style={[
            styles.modeBtn,
            ledState.mode === 'animation' && styles.modeBtnActive,
          ]}
          onPress={() => send('mode_animation')}
          activeOpacity={0.6}
        >
          <Text style={styles.modeBtnText}>ANIMATION</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[
            styles.modeBtn,
            ledState.mode === 'static' && styles.modeBtnActive,
          ]}
          onPress={() => send('mode_static')}
          activeOpacity={0.6}
        >
          <Text style={styles.modeBtnText}>STATIC</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[
            styles.modeBtn,
            styles.toggleBtn,
            !ledState.enabled && styles.toggleBtnOff,
          ]}
          onPress={() => send('toggle')}
          activeOpacity={0.6}
        >
          <Text style={styles.modeBtnText}>{ledState.enabled ? 'ON' : 'OFF'}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111',
    paddingHorizontal: 20,
    paddingTop: 20,
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#fff',
    textAlign: 'center',
    marginBottom: 16,
    letterSpacing: 2,
  },

  // Connection
  connectionRow: {
    flexDirection: 'row',
    marginBottom: 16,
    gap: 10,
  },
  ipInput: {
    flex: 1,
    backgroundColor: '#222',
    color: '#fff',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 16,
    borderWidth: 1,
    borderColor: '#333',
  },
  connectBtn: {
    backgroundColor: '#2a7',
    borderRadius: 8,
    paddingHorizontal: 18,
    justifyContent: 'center',
  },
  disconnectBtn: {
    backgroundColor: '#a33',
  },
  connectBtnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 14,
  },

  // Status
  statusBox: {
    backgroundColor: '#1a1a1a',
    borderRadius: 10,
    padding: 14,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#2a2a2a',
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  statusLabel: {
    color: '#888',
    fontSize: 14,
  },
  statusValue: {
    color: '#ddd',
    fontSize: 14,
    fontWeight: '600',
    flexShrink: 1,
    textAlign: 'right',
  },
  statusOn: {
    color: '#4f4',
  },
  statusOff: {
    color: '#f44',
  },
  brightnessBarBg: {
    height: 6,
    backgroundColor: '#333',
    borderRadius: 3,
    marginTop: 4,
    overflow: 'hidden',
  },
  brightnessBarFg: {
    height: '100%',
    backgroundColor: '#fb0',
    borderRadius: 3,
  },

  // D-Pad
  dpad: {
    alignItems: 'center',
    marginBottom: 24,
  },
  dpadRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  dpadSpacer: {
    width: 90,
    height: 80,
  },
  dpadCenter: {
    width: 20,
    height: 80,
  },
  dpadBtn: {
    width: 90,
    height: 80,
    backgroundColor: '#2a2a2a',
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#444',
  },
  dpadUp: {
    marginBottom: 6,
    backgroundColor: '#1a3a2a',
    borderColor: '#2a7',
  },
  dpadDown: {
    marginTop: 6,
    backgroundColor: '#3a1a1a',
    borderColor: '#a33',
  },
  dpadLeft: {
    marginRight: 0,
  },
  dpadRight: {
    marginLeft: 0,
  },
  dpadBtnIcon: {
    color: '#fff',
    fontSize: 24,
    fontWeight: 'bold',
  },
  dpadBtnLabel: {
    color: '#aaa',
    fontSize: 10,
    marginTop: 2,
    letterSpacing: 1,
  },

  // Mode buttons
  modeRow: {
    flexDirection: 'row',
    gap: 10,
  },
  modeBtn: {
    flex: 1,
    backgroundColor: '#2a2a2a',
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#444',
  },
  modeBtnActive: {
    backgroundColor: '#1a3a5a',
    borderColor: '#39f',
  },
  toggleBtn: {
    backgroundColor: '#1a3a2a',
    borderColor: '#2a7',
  },
  toggleBtnOff: {
    backgroundColor: '#3a1a1a',
    borderColor: '#a33',
  },
  modeBtnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 13,
    letterSpacing: 1,
  },
});
