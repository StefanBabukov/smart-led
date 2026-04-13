import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  TextInput,
  SafeAreaView,
  StatusBar,
  ScrollView,
  Modal,
  ActivityIndicator,
  Dimensions,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = '@smart_led_ip';
const WS_PORT = 8765;
const RECONNECT_DELAY = 2000;
const MAX_LOGS = 100;
const NUM_LEDS = 300;
const SCREEN_WIDTH = Dimensions.get('window').width;
const WHEEL_SEND_INTERVAL = 32;
const BRIGHTNESS_SEND_INTERVAL = 32;
const PAINT_SEND_INTERVAL = 32;
const FREE_PAINT_BRUSH_RADIUS = 1;
const NOISY_ACTIONS = new Set(['set_color', 'set_brightness', 'set_pixel_range']);

// --- Color Wheel Helpers ---

function hsvToRgb(h, s, v) {
  h = h % 360;
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r, g, b;
  if (h < 60) { r = c; g = x; b = 0; }
  else if (h < 120) { r = x; g = c; b = 0; }
  else if (h < 180) { r = 0; g = c; b = x; }
  else if (h < 240) { r = 0; g = x; b = c; }
  else if (h < 300) { r = x; g = 0; b = c; }
  else { r = c; g = 0; b = x; }
  return {
    r: Math.round((r + m) * 255),
    g: Math.round((g + m) * 255),
    b: Math.round((b + m) * 255),
  };
}

function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}

const QUICK_COLORS = [
  { name: 'White', r: 255, g: 255, b: 255 },
  { name: 'Warm', r: 255, g: 147, b: 41 },
  { name: 'Cool', r: 200, g: 220, b: 255 },
];

// Generate smooth wheel segments: dense overlapping dots
const WHEEL_SIZE_SMALL = 220;
const WHEEL_SIZE_LARGE = 340;

function generateWheelSegments(wheelSize) {
  const segments = [];
  const wheelRadius = wheelSize / 2;
  const dotSize = wheelSize > 300 ? 8 : 9;
  const ringSpacing = wheelSize > 300 ? 7 : 6;
  const ringCount = Math.floor((wheelRadius - 14) / ringSpacing);

  for (let ring = 0; ring < ringCount; ring++) {
    const radius = 14 + ring * ringSpacing;
    const saturation = Math.min(1, radius / (wheelRadius - 5));
    const circumference = 2 * Math.PI * radius;
    const count = Math.max(12, Math.floor(circumference / (dotSize * 1.4)));

    for (let i = 0; i < count; i++) {
      const hue = (i / count) * 360;
      const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
      const { r, g, b } = hsvToRgb(hue, saturation, 1);
      segments.push({
        x: wheelRadius + radius * Math.cos(angle) - dotSize / 2,
        y: wheelRadius + radius * Math.sin(angle) - dotSize / 2,
        size: dotSize,
        color: rgbToHex(r, g, b),
      });
    }
  }
  return segments;
}

// --- Main App ---

export default function App() {
  const [ip, setIp] = useState('192.168.1.100');
  const [connected, setConnected] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState([]);
  const [ledState, setLedState] = useState({
    mode: 'animation',
    effect_name: '',
    effect_index: 0,
    brightness: 255,
    enabled: true,
    total_effects: 20,
    color: null,
  });

  // Scan state
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [foundDevices, setFoundDevices] = useState([]);
  const [showScanModal, setShowScanModal] = useState(false);
  const scanCancelled = useRef(false);
  const [scrollEnabled, setScrollEnabled] = useState(true);

  const [wheelExpanded, setWheelExpanded] = useState(false);
  const wheelSize = wheelExpanded ? WHEEL_SIZE_LARGE : WHEEL_SIZE_SMALL;
  const wheelRadius = wheelSize / 2;

  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const intentionalClose = useRef(false);
  const logScrollRef = useRef(null);

  // Brightness: use local state to avoid jiggle from server broadcasts
  const lastBrightnessSend = useRef(0);
  const brightnessBarLayout = useRef({ x: 0, width: 0 });
  const [localBrightness, setLocalBrightness] = useState(null);
  const isDraggingBrightness = useRef(false);
  const brightnessReleaseTimer = useRef(null);
  const lastBrightnessValue = useRef(null);

  // Free paint state
  const [freePaintMode, setFreePaintMode] = useState(false);
  const [ledColors, setLedColors] = useState(
    () => Array.from({ length: NUM_LEDS }, () => ({ r: 0, g: 0, b: 0 }))
  );
  const [paintColor, setPaintColor] = useState({ r: 255, g: 0, b: 0 });
  const lastPaintSend = useRef(0);
  const stripBarLayout = useRef({ x: 0, width: 0 });
  const lastPaintIndex = useRef(null);
  const lastWheelSend = useRef(0);
  const lastWheelColor = useRef('');

  const wheelSegments = useMemo(() => generateWheelSegments(wheelSize), [wheelSize]);
  const wheelDotViews = useMemo(() => (
    wheelSegments.map((seg, i) => (
      <View
        key={i}
        pointerEvents="none"
        style={[
          styles.wheelDot,
          {
            left: seg.x,
            top: seg.y,
            width: seg.size,
            height: seg.size,
            borderRadius: seg.size / 2,
            backgroundColor: seg.color,
          },
        ]}
      />
    ))
  ), [wheelSegments]);

  const addLog = useCallback((msg, level = 'info') => {
    const time = new Date().toLocaleTimeString('en-GB', { hour12: false });
    setLogs((prev) => {
      const next = [...prev, { time, msg, level }];
      return next.length > MAX_LOGS ? next.slice(-MAX_LOGS) : next;
    });
  }, []);

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
    if (brightnessReleaseTimer.current) {
      clearTimeout(brightnessReleaseTimer.current);
      brightnessReleaseTimer.current = null;
    }
    if (wsRef.current) {
      intentionalClose.current = true;
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const connect = useCallback((connectIp) => {
    const targetIp = connectIp || ip;
    cleanup();
    intentionalClose.current = false;

    AsyncStorage.setItem(STORAGE_KEY, targetIp);
    if (connectIp) setIp(targetIp);

    const url = `ws://${targetIp}:${WS_PORT}`;
    addLog(`Connecting to ${url}...`);

    const ws = new WebSocket(url);

    ws.onopen = () => {
      addLog('Connected!', 'success');
      setConnected(true);
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'state') {
          setLedState(data);
          // Only sync brightness from server when not dragging
          if (!isDraggingBrightness.current) {
            setLocalBrightness(data.brightness);
            lastBrightnessValue.current = data.brightness;
          }
        } else if (data.type === 'strip_colors') {
          setLedColors(data.colors.map(c => ({ r: c[0], g: c[1], b: c[2] })));
        }
      } catch (err) {
        addLog(`Parse error: ${err.message}`, 'error');
      }
    };

    ws.onclose = (e) => {
      addLog(`Disconnected (code=${e.code})`, 'warn');
      setConnected(false);
      wsRef.current = null;
      if (!intentionalClose.current) {
        reconnectTimer.current = setTimeout(() => connect(targetIp), RECONNECT_DELAY);
      }
    };

    ws.onerror = (e) => {
      addLog(`WebSocket error: ${e.message || 'connection failed'}`, 'error');
    };

    wsRef.current = ws;
  }, [ip, cleanup, addLog]);

  const disconnect = useCallback(() => {
    addLog('Disconnecting...');
    cleanup();
  }, [cleanup, addLog]);

  const send = useCallback((action, extra = {}, options = {}) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action, ...extra }));
      if (!options.silent && !NOISY_ACTIONS.has(action)) {
        addLog(`Sent: ${action}${Object.keys(extra).length ? ' ' + JSON.stringify(extra) : ''}`);
      }
    } else {
      addLog(`Cannot send "${action}" - not connected`, 'error');
    }
  }, [addLog]);

  // Cleanup on unmount
  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  // --- Network Scan ---
  const scanNetwork = useCallback(async () => {
    setScanning(true);
    setFoundDevices([]);
    setScanProgress(0);
    scanCancelled.current = false;
    setShowScanModal(true);

    const subnet = ip.split('.').slice(0, 3).join('.') + '.';
    const found = [];
    const batchSize = 25;

    for (let batch = 0; batch < 254 && !scanCancelled.current; batch += batchSize) {
      const promises = [];
      for (let i = batch + 1; i <= Math.min(batch + batchSize, 254); i++) {
        const testIp = subnet + i;
        promises.push(
          new Promise((resolve) => {
            let resolved = false;
            const done = (result) => { if (!resolved) { resolved = true; resolve(result); } };
            const timeout = setTimeout(() => done(null), 800);
            try {
              const ws = new WebSocket(`ws://${testIp}:${WS_PORT}`);
              ws.onmessage = (e) => {
                try {
                  const data = JSON.parse(e.data);
                  if (data.type === 'state') {
                    clearTimeout(timeout);
                    ws.close();
                    done(testIp);
                    return;
                  }
                } catch {}
                clearTimeout(timeout);
                ws.close();
                done(null);
              };
              ws.onerror = () => { clearTimeout(timeout); try { ws.close(); } catch {} done(null); };
              ws.onclose = () => { clearTimeout(timeout); done(null); };
            } catch {
              clearTimeout(timeout);
              done(null);
            }
          })
        );
      }
      const results = await Promise.all(promises);
      results.filter(Boolean).forEach(foundIp => {
        if (!found.includes(foundIp)) found.push(foundIp);
      });
      setFoundDevices([...found]);
      setScanProgress(Math.min(batch + batchSize, 254));
    }
    setScanning(false);
  }, [ip]);

  const cancelScan = useCallback(() => {
    scanCancelled.current = true;
    setScanning(false);
    setShowScanModal(false);
  }, []);

  const selectDevice = useCallback((deviceIp) => {
    setShowScanModal(false);
    setScanning(false);
    connect(deviceIp);
  }, [connect]);

  const beginInteractiveGesture = useCallback(() => {
    setScrollEnabled(false);
  }, []);

  const endInteractiveGesture = useCallback(() => {
    setScrollEnabled(true);
  }, []);

  // --- Color Wheel Touch ---
  const handleWheelTouch = useCallback((evt, forceSend = false) => {
    const { locationX, locationY } = evt.nativeEvent;
    const dx = locationX - wheelRadius;
    const dy = locationY - wheelRadius;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist > wheelRadius) return;

    let r, g, b;
    if (dist < Math.max(18, wheelRadius * 0.18)) {
      r = 255; g = 255; b = 255;
    } else {
      const angle = Math.atan2(dy, dx);
      const hue = ((angle * 180) / Math.PI + 90 + 360) % 360;
      const saturation = Math.min(1, dist / wheelRadius);
      ({ r, g, b } = hsvToRgb(hue, saturation, 1));
    }

    if (freePaintMode) {
      setPaintColor({ r, g, b });
    } else {
      const now = Date.now();
      const colorKey = `${r},${g},${b}`;
      if (
        forceSend ||
        (colorKey !== lastWheelColor.current && now - lastWheelSend.current >= WHEEL_SEND_INTERVAL)
      ) {
        lastWheelColor.current = colorKey;
        lastWheelSend.current = now;
        send('set_color', { r, g, b }, { silent: true });
      }
    }
  }, [send, wheelRadius, freePaintMode]);

  const handleWheelGrant = useCallback((evt) => {
    beginInteractiveGesture();
    handleWheelTouch(evt, true);
  }, [beginInteractiveGesture, handleWheelTouch]);

  const handleWheelRelease = useCallback((evt) => {
    handleWheelTouch(evt, true);
    endInteractiveGesture();
  }, [endInteractiveGesture, handleWheelTouch]);

  // --- Brightness Slider Touch ---
  const updateBrightnessFromTouch = useCallback((evt, forceSend = false) => {
    const x = evt.nativeEvent.locationX;
    const width = brightnessBarLayout.current.width;
    if (width <= 0) return null;
    const value = Math.round(Math.max(0, Math.min(255, (x / width) * 255)));
    setLocalBrightness(value);
    const now = Date.now();
    if (
      forceSend ||
      (value !== lastBrightnessValue.current && now - lastBrightnessSend.current >= BRIGHTNESS_SEND_INTERVAL)
    ) {
      lastBrightnessSend.current = now;
      lastBrightnessValue.current = value;
      send('set_brightness', { value }, { silent: true });
    }
    return value;
  }, [send]);

  const handleBrightnessStart = useCallback((evt) => {
    if (brightnessReleaseTimer.current) {
      clearTimeout(brightnessReleaseTimer.current);
      brightnessReleaseTimer.current = null;
    }
    isDraggingBrightness.current = true;
    beginInteractiveGesture();
    updateBrightnessFromTouch(evt, true);
  }, [beginInteractiveGesture, updateBrightnessFromTouch]);

  const handleBrightnessMove = useCallback((evt) => {
    updateBrightnessFromTouch(evt);
  }, [updateBrightnessFromTouch]);

  const handleBrightnessRelease = useCallback((evt) => {
    updateBrightnessFromTouch(evt, true);
    brightnessReleaseTimer.current = setTimeout(() => {
      isDraggingBrightness.current = false;
      brightnessReleaseTimer.current = null;
    }, 150);
    endInteractiveGesture();
  }, [endInteractiveGesture, updateBrightnessFromTouch]);

  const handleBrightnessTerminate = useCallback(() => {
    if (brightnessReleaseTimer.current) {
      clearTimeout(brightnessReleaseTimer.current);
      brightnessReleaseTimer.current = null;
    }
    isDraggingBrightness.current = false;
    endInteractiveGesture();
  }, [endInteractiveGesture]);

  // --- Free Paint ---
  const toggleFreePaint = useCallback(() => {
    const entering = !freePaintMode;
    setFreePaintMode(entering);
    if (entering) {
      send('get_strip_colors');
    }
  }, [freePaintMode, send]);

  const paintStripRange = useCallback((fromIndex, toIndex, forceSend = false) => {
    const { r, g, b } = paintColor;
    const brushStart = Math.max(0, Math.min(fromIndex, toIndex) - FREE_PAINT_BRUSH_RADIUS);
    const brushEnd = Math.min(NUM_LEDS - 1, Math.max(fromIndex, toIndex) + FREE_PAINT_BRUSH_RADIUS);

    setLedColors(prev => {
      const next = [...prev];
      for (let i = brushStart; i <= brushEnd; i++) {
        next[i] = { r, g, b };
      }
      return next;
    });

    const now = Date.now();
    if (forceSend || now - lastPaintSend.current >= PAINT_SEND_INTERVAL) {
      lastPaintSend.current = now;
      send('set_pixel_range', { start: brushStart, end: brushEnd, r, g, b }, { silent: true });
    }
  }, [paintColor, send]);

  const getStripLedIndex = useCallback((evt) => {
    const x = evt.nativeEvent.locationX;
    const width = stripBarLayout.current.width;
    if (width <= 0) return null;
    return Math.floor(Math.max(0, Math.min(NUM_LEDS - 1, (x / width) * NUM_LEDS)));
  }, []);

  const handleStripTouch = useCallback((evt, forceSend = false) => {
    const ledIndex = getStripLedIndex(evt);
    if (ledIndex === null) return;

    const startIndex = lastPaintIndex.current ?? ledIndex;
    paintStripRange(startIndex, ledIndex, forceSend);
    lastPaintIndex.current = ledIndex;
  }, [getStripLedIndex, paintStripRange]);

  const handleStripGrant = useCallback((evt) => {
    beginInteractiveGesture();
    lastPaintIndex.current = null;
    handleStripTouch(evt, true);
  }, [beginInteractiveGesture, handleStripTouch]);

  const handleStripRelease = useCallback((evt) => {
    handleStripTouch(evt, true);
    lastPaintIndex.current = null;
    endInteractiveGesture();
  }, [endInteractiveGesture, handleStripTouch]);

  const resetFreePaint = useCallback(() => {
    const black = Array.from({ length: NUM_LEDS }, () => ({ r: 0, g: 0, b: 0 }));
    setLedColors(black);
    send('set_pixel_range', { start: 0, end: NUM_LEDS - 1, r: 0, g: 0, b: 0 }, { silent: true });
  }, [send]);

  // --- Derived values ---
  const displayBrightness = localBrightness !== null ? localBrightness : ledState.brightness;
  const brightnessPercent = Math.round((displayBrightness / 255) * 100);
  const barWidth = `${brightnessPercent}%`;
  const logColors = { info: '#888', success: '#4f4', warn: '#fb0', error: '#f44' };

  const currentColorHex = ledState.color
    ? rgbToHex(ledState.color.r, ledState.color.g, ledState.color.b)
    : '#ff0000';

  // Compute strip LED width to fit screen
  const stripPadding = 40; // account for parent padding
  const stripWidth = SCREEN_WIDTH - stripPadding;
  const ledWidth = stripWidth / NUM_LEDS;

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#111" />
      <ScrollView
        style={styles.scrollContainer}
        contentContainerStyle={styles.scrollContent}
        scrollEnabled={scrollEnabled}
      >

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
          <TouchableOpacity style={styles.scanBtn} onPress={scanNetwork} activeOpacity={0.6}>
            <Text style={styles.scanBtnText}>Scan</Text>
          </TouchableOpacity>
          {!connected ? (
            <TouchableOpacity style={styles.connectBtn} onPress={() => connect()}>
              <Text style={styles.connectBtnText}>Connect</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={[styles.connectBtn, styles.disconnectBtn]} onPress={disconnect}>
              <Text style={styles.connectBtnText}>Disconnect</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Status Panel */}
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
            <Text style={styles.statusLabel}>
              {ledState.mode === 'animation' ? 'Effect' : 'Color'}
            </Text>
            <View style={styles.statusValueRow}>
              {ledState.mode === 'static' && ledState.color && (
                <View style={[styles.colorPreview, { backgroundColor: currentColorHex }]} />
              )}
              <Text style={styles.statusValue} numberOfLines={1}>
                {ledState.mode === 'animation'
                  ? `${ledState.effect_name} (${ledState.effect_index + 1}/${ledState.total_effects})`
                  : ledState.color
                    ? `R:${ledState.color.r} G:${ledState.color.g} B:${ledState.color.b}`
                    : ledState.effect_name
                }
              </Text>
            </View>
          </View>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Power</Text>
            <Text style={[styles.statusValue, ledState.enabled ? styles.statusOn : styles.statusOff]}>
              {ledState.enabled ? 'ON' : 'OFF'}
            </Text>
          </View>
        </View>

        {/* Mode Tabs */}
        <View style={styles.modeRow}>
          <TouchableOpacity
            style={[styles.modeBtn, ledState.mode === 'animation' && styles.modeBtnActive]}
            onPress={() => send('mode_animation')}
            activeOpacity={0.6}
          >
            <Text style={styles.modeBtnText}>ANIMATION</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.modeBtn, ledState.mode === 'static' && styles.modeBtnActive]}
            onPress={() => send('mode_static')}
            activeOpacity={0.6}
          >
            <Text style={styles.modeBtnText}>STATIC</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.modeBtn, styles.toggleBtn, !ledState.enabled && styles.toggleBtnOff]}
            onPress={() => send('toggle')}
            activeOpacity={0.6}
          >
            <Text style={styles.modeBtnText}>{ledState.enabled ? 'ON' : 'OFF'}</Text>
          </TouchableOpacity>
        </View>

        {/* Context-Sensitive Controls */}
        {ledState.mode === 'animation' ? (
          /* Animation: PREV / effect name / NEXT */
          <View style={styles.animControlRow}>
            <TouchableOpacity
              style={styles.animNavBtn}
              onPress={() => send('previous')}
              activeOpacity={0.6}
            >
              <Text style={styles.animNavIcon}>{'\u2190'}</Text>
              <Text style={styles.animNavLabel}>PREV</Text>
            </TouchableOpacity>
            <View style={styles.animEffectBox}>
              <Text style={styles.animEffectName} numberOfLines={2}>
                {ledState.effect_name}
              </Text>
              <Text style={styles.animEffectIndex}>
                {ledState.effect_index + 1} / {ledState.total_effects}
              </Text>
            </View>
            <TouchableOpacity
              style={styles.animNavBtn}
              onPress={() => send('next')}
              activeOpacity={0.6}
            >
              <Text style={styles.animNavIcon}>{'\u2192'}</Text>
              <Text style={styles.animNavLabel}>NEXT</Text>
            </TouchableOpacity>
          </View>
        ) : (
          /* Static: Color Wheel */
          <View style={styles.colorSection}>
            {/* Sub-mode toggle: Solid Color / Free Paint */}
            <View style={styles.paintToggleRow}>
              <TouchableOpacity
                style={[styles.paintToggleBtn, !freePaintMode && styles.paintToggleBtnActive]}
                onPress={() => setFreePaintMode(false)}
                activeOpacity={0.6}
              >
                <Text style={styles.paintToggleBtnText}>Solid Color</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.paintToggleBtn, freePaintMode && styles.paintToggleBtnActive]}
                onPress={toggleFreePaint}
                activeOpacity={0.6}
              >
                <Text style={styles.paintToggleBtnText}>Free Paint</Text>
              </TouchableOpacity>
            </View>

            {/* Color Wheel */}
            <View
              style={[styles.wheelContainer, { width: wheelSize, height: wheelSize }]}
              onStartShouldSetResponderCapture={() => true}
              onMoveShouldSetResponderCapture={() => true}
              onStartShouldSetResponder={() => true}
              onMoveShouldSetResponder={() => true}
              onResponderTerminationRequest={() => false}
              onResponderGrant={handleWheelGrant}
              onResponderMove={handleWheelTouch}
              onResponderRelease={handleWheelRelease}
              onResponderTerminate={endInteractiveGesture}
            >
              <View
                pointerEvents="none"
                style={[styles.wheelBg, { width: wheelSize, height: wheelSize, borderRadius: wheelSize / 2 }]}
              />
              {wheelDotViews}
              <View
                pointerEvents="none"
                style={[styles.wheelCenter, { left: wheelSize / 2 - 16, top: wheelSize / 2 - 16 }]}
              />
            </View>

            {/* Expand / Shrink toggle */}
            <TouchableOpacity
              style={styles.wheelExpandBtn}
              onPress={() => setWheelExpanded(prev => !prev)}
              activeOpacity={0.6}
            >
              <Text style={styles.wheelExpandBtnText}>
                {wheelExpanded ? 'Shrink' : 'Expand'}
              </Text>
            </TouchableOpacity>

            {/* Paint color indicator (free paint only) */}
            {freePaintMode && (
              <View style={styles.paintColorRow}>
                <Text style={styles.paintColorLabel}>Paint Color:</Text>
                <View style={[styles.paintColorSwatch, {
                  backgroundColor: rgbToHex(paintColor.r, paintColor.g, paintColor.b),
                }]} />
              </View>
            )}

            {/* Quick-pick colors */}
            {!freePaintMode && (
              <View style={styles.quickColorRow}>
                {QUICK_COLORS.map((c) => (
                  <TouchableOpacity
                    key={c.name}
                    style={[styles.quickColorBtn, { borderColor: rgbToHex(c.r, c.g, c.b) + '88' }]}
                    onPress={() => send('set_color', { r: c.r, g: c.g, b: c.b })}
                    activeOpacity={0.6}
                  >
                    <View style={[styles.quickColorDot, { backgroundColor: rgbToHex(c.r, c.g, c.b) }]} />
                    <Text style={styles.quickColorLabel}>{c.name}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {/* LED Strip Visualization (free paint only) */}
            {freePaintMode && (
              <View style={styles.stripSection}>
                <Text style={styles.stripLabel}>LED Strip (drag to paint)</Text>
                <View
                  style={[styles.stripBar, { width: stripWidth }]}
                  onLayout={(e) => { stripBarLayout.current = e.nativeEvent.layout; }}
                  onStartShouldSetResponderCapture={() => true}
                  onMoveShouldSetResponderCapture={() => true}
                  onStartShouldSetResponder={() => true}
                  onMoveShouldSetResponder={() => true}
                  onResponderTerminationRequest={() => false}
                  onResponderGrant={handleStripGrant}
                  onResponderMove={handleStripTouch}
                  onResponderRelease={handleStripRelease}
                  onResponderTerminate={() => {
                    lastPaintIndex.current = null;
                    endInteractiveGesture();
                  }}
                >
                  {ledColors.map((c, i) => (
                    <View
                      key={i}
                      pointerEvents="none"
                      style={{
                        width: ledWidth,
                        height: 50,
                        backgroundColor: (c.r === 0 && c.g === 0 && c.b === 0)
                          ? '#1a1a1a'
                          : rgbToHex(c.r, c.g, c.b),
                      }}
                    />
                  ))}
                </View>
                <TouchableOpacity
                  style={styles.resetBtn}
                  onPress={resetFreePaint}
                  activeOpacity={0.6}
                >
                  <Text style={styles.resetBtnText}>Reset Strip</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {/* Brightness Slider */}
        <View style={styles.brightnessSection}>
          <View style={styles.brightnessHeader}>
            <Text style={styles.brightnessTitle}>Brightness</Text>
            <Text style={styles.brightnessPercent}>{brightnessPercent}%</Text>
          </View>
          <View
            style={styles.brightnessTrack}
            onLayout={(e) => { brightnessBarLayout.current = e.nativeEvent.layout; }}
            onStartShouldSetResponderCapture={() => true}
            onMoveShouldSetResponderCapture={() => true}
            onStartShouldSetResponder={() => true}
            onMoveShouldSetResponder={() => true}
            onResponderTerminationRequest={() => false}
            onResponderGrant={handleBrightnessStart}
            onResponderMove={handleBrightnessMove}
            onResponderRelease={handleBrightnessRelease}
            onResponderTerminate={handleBrightnessTerminate}
          >
            <View pointerEvents="none" style={[styles.brightnessFill, { width: barWidth }]} />
            <View pointerEvents="none" style={[styles.brightnessThumb, { left: barWidth }]} />
          </View>
        </View>

        {/* Debug Log Toggle */}
        <TouchableOpacity
          style={styles.logToggle}
          onPress={() => setShowLogs(!showLogs)}
          activeOpacity={0.6}
        >
          <Text style={styles.logToggleText}>
            {showLogs ? 'HIDE LOGS' : 'SHOW LOGS'} ({logs.length})
          </Text>
        </TouchableOpacity>

        {/* Debug Log Panel */}
        {showLogs && (
          <View style={styles.logPanel}>
            <View style={styles.logHeader}>
              <Text style={styles.logHeaderText}>Debug Logs</Text>
              <TouchableOpacity onPress={() => setLogs([])}>
                <Text style={styles.logClearText}>Clear</Text>
              </TouchableOpacity>
            </View>
            <ScrollView
              ref={logScrollRef}
              style={styles.logScroll}
              nestedScrollEnabled
              onContentSizeChange={() => logScrollRef.current?.scrollToEnd({ animated: false })}
            >
              {logs.map((log, i) => (
                <Text key={i} style={[styles.logLine, { color: logColors[log.level] || '#888' }]}>
                  <Text style={styles.logTime}>{log.time}</Text> {log.msg}
                </Text>
              ))}
              {logs.length === 0 && (
                <Text style={styles.logEmpty}>No logs yet. Try connecting.</Text>
              )}
            </ScrollView>
          </View>
        )}
      </ScrollView>

      {/* Scan Modal */}
      <Modal
        visible={showScanModal}
        transparent
        animationType="fade"
        onRequestClose={cancelScan}
      >
        <View style={styles.scanOverlay}>
          <View style={styles.scanModal}>
            <Text style={styles.scanTitle}>Scan for Smart LED</Text>

            {scanning && (
              <View style={styles.scanProgressSection}>
                <View style={styles.scanProgressRow}>
                  <ActivityIndicator color="#39f" size="small" />
                  <Text style={styles.scanProgressText}>
                    Scanning... {scanProgress}/254
                  </Text>
                </View>
                <View style={styles.scanProgressBarBg}>
                  <View style={[styles.scanProgressBarFg, { width: `${(scanProgress / 254) * 100}%` }]} />
                </View>
              </View>
            )}

            {!scanning && foundDevices.length === 0 && (
              <Text style={styles.scanEmpty}>No devices found on {ip.split('.').slice(0, 3).join('.')}.x</Text>
            )}

            {foundDevices.length > 0 && (
              <View style={styles.scanList}>
                <Text style={styles.scanListHeader}>Found devices:</Text>
                {foundDevices.map((deviceIp) => (
                  <TouchableOpacity
                    key={deviceIp}
                    style={styles.scanItem}
                    onPress={() => selectDevice(deviceIp)}
                    activeOpacity={0.6}
                  >
                    <Text style={styles.scanItemText}>{deviceIp}</Text>
                    <Text style={styles.scanItemHint}>Tap to connect</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            <TouchableOpacity style={styles.scanCancelBtn} onPress={cancelScan} activeOpacity={0.6}>
              <Text style={styles.scanCancelText}>{scanning ? 'Cancel' : 'Close'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// --- Styles ---

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111',
  },
  scrollContainer: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 30,
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
    gap: 8,
  },
  ipInput: {
    flex: 1,
    backgroundColor: '#222',
    color: '#fff',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    borderWidth: 1,
    borderColor: '#333',
  },
  scanBtn: {
    backgroundColor: '#2a3a5a',
    borderRadius: 8,
    paddingHorizontal: 14,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#39f',
  },
  scanBtnText: {
    color: '#39f',
    fontWeight: 'bold',
    fontSize: 13,
  },
  connectBtn: {
    backgroundColor: '#2a7',
    borderRadius: 8,
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  disconnectBtn: {
    backgroundColor: '#a33',
  },
  connectBtnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 13,
  },

  // Status
  statusBox: {
    backgroundColor: '#1a1a1a',
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#2a2a2a',
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 5,
  },
  statusLabel: {
    color: '#888',
    fontSize: 13,
  },
  statusValue: {
    color: '#ddd',
    fontSize: 13,
    fontWeight: '600',
    flexShrink: 1,
    textAlign: 'right',
  },
  statusValueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexShrink: 1,
  },
  colorPreview: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#555',
  },
  statusOn: { color: '#4f4' },
  statusOff: { color: '#f44' },

  // Mode buttons
  modeRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
  },
  modeBtn: {
    flex: 1,
    backgroundColor: '#2a2a2a',
    borderRadius: 10,
    paddingVertical: 14,
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

  // Animation controls
  animControlRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 16,
    gap: 12,
  },
  animNavBtn: {
    width: 80,
    height: 70,
    backgroundColor: '#2a2a2a',
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#444',
  },
  animNavIcon: {
    color: '#fff',
    fontSize: 24,
    fontWeight: 'bold',
  },
  animNavLabel: {
    color: '#aaa',
    fontSize: 10,
    marginTop: 2,
    letterSpacing: 1,
  },
  animEffectBox: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  animEffectName: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
  animEffectIndex: {
    color: '#888',
    fontSize: 12,
    marginTop: 4,
  },

  // Color wheel section
  colorSection: {
    alignItems: 'center',
    marginVertical: 16,
  },
  wheelContainer: {
    position: 'relative',
  },
  wheelBg: {
    position: 'absolute',
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: '#333',
  },
  wheelDot: {
    position: 'absolute',
  },
  wheelCenter: {
    position: 'absolute',
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#fff',
    borderWidth: 2,
    borderColor: '#ddd',
  },
  wheelExpandBtn: {
    marginTop: 10,
    paddingVertical: 6,
    paddingHorizontal: 18,
    backgroundColor: '#2a2a2a',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#444',
  },
  wheelExpandBtnText: {
    color: '#aaa',
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 1,
  },
  quickColorRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
  quickColorBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a1a',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
    gap: 8,
    borderWidth: 1,
  },
  quickColorDot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 1,
    borderColor: '#555',
  },
  quickColorLabel: {
    color: '#ccc',
    fontSize: 12,
    fontWeight: '600',
  },

  // Free paint
  paintToggleRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
    width: '100%',
  },
  paintToggleBtn: {
    flex: 1,
    backgroundColor: '#2a2a2a',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#444',
  },
  paintToggleBtnActive: {
    backgroundColor: '#1a3a5a',
    borderColor: '#39f',
  },
  paintToggleBtnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 12,
    letterSpacing: 1,
  },
  paintColorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginTop: 12,
  },
  paintColorLabel: {
    color: '#aaa',
    fontSize: 12,
    fontWeight: '600',
  },
  paintColorSwatch: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: '#555',
  },
  stripSection: {
    width: '100%',
    marginTop: 16,
  },
  stripLabel: {
    color: '#888',
    fontSize: 12,
    marginBottom: 8,
    letterSpacing: 1,
  },
  stripBar: {
    flexDirection: 'row',
    height: 50,
    borderRadius: 8,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#333',
    backgroundColor: '#0a0a0a',
  },
  resetBtn: {
    marginTop: 10,
    alignItems: 'center',
    paddingVertical: 8,
    backgroundColor: '#3a1a1a',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#a33',
  },
  resetBtnText: {
    color: '#f44',
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 1,
  },

  // Brightness slider
  brightnessSection: {
    marginVertical: 16,
  },
  brightnessHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  brightnessTitle: {
    color: '#aaa',
    fontSize: 13,
    fontWeight: '600',
    letterSpacing: 1,
  },
  brightnessPercent: {
    color: '#fb0',
    fontSize: 13,
    fontWeight: '700',
  },
  brightnessTrack: {
    height: 40,
    backgroundColor: '#2a2a2a',
    borderRadius: 20,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#444',
    justifyContent: 'center',
  },
  brightnessFill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: '#fb0',
    borderRadius: 20,
  },
  brightnessThumb: {
    position: 'absolute',
    width: 6,
    height: 28,
    backgroundColor: '#fff',
    borderRadius: 3,
    marginLeft: -3,
    top: 6,
  },

  // Log toggle
  logToggle: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  logToggleText: {
    color: '#666',
    fontSize: 12,
    letterSpacing: 1,
  },

  // Log panel
  logPanel: {
    marginTop: 8,
    backgroundColor: '#0a0a0a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#222',
    overflow: 'hidden',
    maxHeight: 200,
  },
  logHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#1a1a1a',
    borderBottomWidth: 1,
    borderBottomColor: '#222',
  },
  logHeaderText: {
    color: '#666',
    fontSize: 11,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  logClearText: {
    color: '#a33',
    fontSize: 11,
    fontWeight: 'bold',
  },
  logScroll: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  logLine: {
    fontSize: 10,
    fontFamily: 'monospace',
    lineHeight: 16,
  },
  logTime: {
    color: '#555',
  },
  logEmpty: {
    color: '#444',
    fontSize: 11,
    textAlign: 'center',
    marginTop: 20,
  },

  // Scan Modal
  scanOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.85)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanModal: {
    backgroundColor: '#1a1a1a',
    borderRadius: 16,
    padding: 24,
    width: '85%',
    maxHeight: '70%',
    borderWidth: 1,
    borderColor: '#333',
  },
  scanTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 16,
  },
  scanProgressSection: {
    marginBottom: 16,
  },
  scanProgressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 8,
  },
  scanProgressText: {
    color: '#aaa',
    fontSize: 13,
  },
  scanProgressBarBg: {
    height: 6,
    backgroundColor: '#333',
    borderRadius: 3,
    overflow: 'hidden',
  },
  scanProgressBarFg: {
    height: '100%',
    backgroundColor: '#39f',
    borderRadius: 3,
  },
  scanEmpty: {
    color: '#888',
    fontSize: 14,
    textAlign: 'center',
    marginVertical: 20,
  },
  scanList: {
    marginBottom: 16,
  },
  scanListHeader: {
    color: '#888',
    fontSize: 12,
    marginBottom: 8,
    letterSpacing: 1,
  },
  scanItem: {
    backgroundColor: '#222',
    borderRadius: 10,
    paddingVertical: 14,
    paddingHorizontal: 16,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#2a7',
  },
  scanItemText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  scanItemHint: {
    color: '#2a7',
    fontSize: 11,
    marginTop: 2,
  },
  scanCancelBtn: {
    alignItems: 'center',
    paddingVertical: 12,
    backgroundColor: '#2a2a2a',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#444',
  },
  scanCancelText: {
    color: '#aaa',
    fontSize: 14,
    fontWeight: '600',
  },
});
