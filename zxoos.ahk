#Requires AutoHotkey v2.0
#SingleInstance Force
#MaxThreadsPerHotkey 255
A_MaxHotkeysPerInterval := 2000
SendMode("Input")
CoordMode("Mouse", "Screen")
DllCall("timeBeginPeriod", "UInt", 1)

global macrosEnabled := true
global rgcRunning := false

; --- Adrenalin Dark / Red Theme ---
cSide := "0D0D11"
cBG   := "121216"
cCard := "18181F"
cLine := "262630"
cAcc  := "F7768E"
cTxt  := "D4D4D8"
cMut  := "71717A"
cIn   := "1F1F28"
cInTx := "F7768E"
cGrn  := "9ECE6A"

; --- Page Variables ---
global curPage := 1
global buildPage := 0
global pageStart := 0
global pages := [[], [], [], [], []]
global pageOf := Map()
global wantVis := Map()

; --- GUI Helpers ---
Card(x, y, w, h) => settings.AddText("x" x " y" y " w" w " h" h " Background" cCard)
Lbl(x, y, t, w := 160) => settings.AddText("x" x " y" y " w" w " h28 0x200 Background" cCard, t)

Head(t, sub := "") {
    h := settings.AddText("x220 y16 w580 h34 0x200", t)
    h.SetFont("s15 bold c" cAcc)
    settings.AddText("x220 y52 w620 h2 Background" cLine)
    if (sub != "") {
        s := settings.AddText("x220 y58 w620 h22 0x200", sub)
        s.SetFont("s9 norm c" cMut)
    }
}

Chk(x, y, t) {
    c := settings.AddCheckBox("x" x " y" y " h28 w280 -Theme Background" cCard, t)
    c.SetFont("s10 bold c" cTxt)
    return c
}

Edt(x, y, v, num := true) => settings.AddEdit("x" x " y" y " w110 h28 Center " (num ? "+Number " : "") "Background" cIn " c" cInTx, v)
Hk(x, y, v)  => settings.AddHotkey("x" x " y" y " w110 h28 Center", v)
Ddl(x, y, items, sel) => settings.AddDropDownList("x" x " y" y " w110 Choose" sel, items)

Btn(y, t, bg, txtColor := "") {
    b := settings.AddText("x16 y" y " w178 h30 Center 0x200 Background" bg, t)
    b.SetFont("s10 bold c" (txtColor != "" ? txtColor : cSide))
    return b
}

; --- Main Window ---
settings := Gui("+Border -Caption", "Zxoos")
settings.BackColor := cBG
settings.SetFont("c" cTxt " s10", "Segoe UI")
DllCall("dwmapi\DwmSetWindowAttribute", "Ptr", settings.Hwnd, "Int", 20, "Int*", 1, "Int", 4)

; --- Sidebar Layout (Adrenalin Style) ---
settings.AddText("x0 y0 w210 h560 Background" cSide)
t1 := settings.AddText("x16 y16 w178 h28 0x200 Background" cSide, "ZXOOS")
t1.SetFont("s14 bold c" cAcc)
settings.AddText("x16 y52 w178 h1 Background" cLine)

navNames := ["Navigation", "Macros", "Backdash", "RGC", "Settings"]
navItems := []
for i, name in navNames {
    if (i = 1) {
        cat := settings.AddText("x16 y" (62 + (i - 1) * 36) " w178 h20 0x200 Background" cSide, "NAVIGATION")
        cat.SetFont("s8 bold c" cMut)
        continue
    }
    idx := i - 1
    n := settings.AddText("x16 y" (50 + (idx * 36)) " w178 h30 0x200 Background" cSide, "    " name)
    n.SetFont("s10 bold c" cMut)
    n.OnEvent("Click", SelectTab.Bind(idx))
    navItems.Push(n)
}
navbar := settings.AddText("x16 y86 w3 h30 Background" cAcc)

presetBtn := Btn(445, "Preset Manager", cCard, cTxt)
about     := Btn(485, "About Hub", cCard, cTxt)

footerTxt := settings.AddText("x220 y525 w620 h24 0x200", "zxoos")
footerTxt.SetFont("s9 bold c" cMut)

closeBtn := settings.AddText("x825 y10 w25 h25 Center 0x200 Background" cAcc, "X")
closeBtn.SetFont("s10 bold c" cSide)
closeBtn.OnEvent("Click", exitmacro)

LX := 220, LF := 400, RX := 540, RF := 720

; ---------------- 1. MACROS ----------------
BeginPage(1)
Head("MACROS CONFIG", "Configure automated combat macros and flicks")
Card(208, 76, 318, 320)
Card(538, 76, 318, 270)
lthmacro := Chk(LX, 86, "Lethal V1")
Lbl(LX, 131, "Hotkey :")
Lbl(LX, 173, "Shiftlock Version :")
Lbl(LX, 215, "Wait For Flick :")
Lbl(LX, 257, "Auto Jump :")
lthtext2 := Lbl(LX, 299, "Dash Style :")
lthtext  := Lbl(LX, 341, "Wait For Flick :")
lthhk        := Hk(LF, 131, "r")
lthshiftlock := Ddl(LF, 173, ["Shiftlock", "Unshiftlock"], 1)
lthsleep     := Edt(LF, 215, "220")
lthjump      := Ddl(LF, 257, ["On", "Off"], 1)
lthdashstyle := Ddl(LF, 299, ["1", "2"], 1)
lthsleep2    := Edt(LF, 341, "200")

lthv2macro := Chk(RX, 86, "Lethal V2")
Lbl(RX, 131, "Hotkey :")
Lbl(RX, 173, "Wait For Flick :")
Lbl(RX, 215, "Auto Jump :")
Lbl(RX, 257, "Dash Style :")
lthv2text := Lbl(RX, 299, "Wait For Flick :")
lthv2hk        := Hk(RF, 131, "r")
lthv2sleep     := Edt(RF, 173, "190")
lthv2jump      := Ddl(RF, 215, ["On", "Off"], 1)
lthv2dashstyle := Ddl(RF, 257, ["1", "2"], 1)
lthv2sleep2    := Edt(RF, 299, "75")

; ---------------- 2. BACKDASH ----------------
BeginPage(2)
Head("BACKDASH CANCEL", "Skill Key + S + Q sequence setup")

bdSet := []
BDCell(x, y, n, hkdef, skilldef) {
    Card(x - 12, y - 8, 318, 120)
    cb := Chk(x, y, "Backdash + " n)
    Lbl(x, y + 36, "Hotkey :", 90)
    hkc := Hk(x + 100, y + 36, hkdef)
    Lbl(x, y + 74, "Skill Key :", 90)
    skc := Edt(x + 100, y + 74, skilldef, false)
    bdSet.Push({ macro: cb, hk: hkc, skill: skc })
}
BDCell(220, 86, 1, "z", "1")
BDCell(550, 86, 2, "x", "2")
BDCell(220, 226, 3, "c", "3")
BDCell(550, 226, 4, "v", "4")

; ---------------- 3. RGC ----------------
BeginPage(3)
Head("RGC MACRO", "Spam side dash while holding M1 & direction key")
Card(208, 76, 318, 230)
Card(538, 76, 318, 230)
rgcmacro := Chk(LX, 86, "RGC")
Lbl(LX, 131, "Hotkey (hold) :")
Lbl(LX, 173, "Dash Direction :")
Lbl(LX, 215, "Spam Delay (ms) :")
Lbl(LX, 257, "Hold M1 :")
rgchk    := Hk(LF, 131, "g")
rgcdash  := Ddl(LF, 173, ["Right", "Left"], 1)
rgcdelay := Edt(LF, 215, "10")
rgchold  := Ddl(LF, 267, ["On", "Off"], 1)

hw := settings.AddText("x" RX " y86 w290 h28 0x200 Background" cCard, "INFO")
hw.SetFont("s10 bold c" cAcc)
hd := settings.AddText("x" RX " y121 w290 h170 Background" cCard, "1. Hold your hotkey.`n2. Macro holds direction key (D/A) and spams Q.`n3. M1 is held down if set to On.`n4. Release key to stop.")
hd.SetFont("s9 norm c" cTxt)

; ---------------- 4. SETTINGS ----------------
BeginPage(4)
Head("SETTINGS & GENERAL", "Configure sensitivity, hotkeys and overlay")
Card(208, 76, 318, 260)
Card(538, 76, 318, 160)
Lbl(LX, 86, "Roblox Sensitivity :")
Lbl(LX, 131, "Exit Macro Hotkey :")
Lbl(LX, 176, "Macro On/Off Hotkey :")
Lbl(LX, 221, "Hide Menu Hotkey :")
Lbl(LX, 266, "Panel Opacity (max 255) :")
robloxsensivity := Edt(LF, 86, "0.4", false)
exithk          := Hk(LF, 131, "F1")
togglehk        := Hk(LF, 176, "F2")
menutogglehk    := Hk(LF, 221, "F3")
hkmenuopacity   := Edt(LF, 266, "220")

hotkeypanel := Chk(RX, 86, "Floating Panel")
cordcheck   := Chk(RX, 131, "Roblox Auto-Sync")
cd := settings.AddText("x" RX " y176 w290 h50 Background" cCard, "Auto-Sync makes the floating panel follow the Roblox window position and hide when Roblox is not active.")
cd.SetFont("s9 norm c" cTxt)
EndPage()

; --- About Window ---
info := Gui("+Border -Caption", "About")
info.BackColor := cBG
info.SetFont("c" cTxt " s10 bold", "Segoe UI")
it := info.AddText("x0 y20 w400 h34 Center 0x200", "zxoos")
it.SetFont("s16 bold c" cAcc)
info.AddText("x40 y65 w320 h80 Center +Wrap", "Custom AutoHotkey macro for Roblox.`nCreated by zxoos.")

dcc  := info.AddText("x130 y180 w140 h36 Center 0x200 Background" cAcc, "DISCORD SERVER")
back := info.AddText("x130 y230 w140 h36 Center 0x200 Background" cCard, "BACK TO MENU")
dcc.SetFont("s10 bold c" cSide)
back.SetFont("s10 bold c" cTxt)

back.OnEvent("Click", backk)
dcc.OnEvent("Click", dcServer)

; --- Preset Window ---
presetGui := Gui("+Border -Caption", "Preset Manager")
presetGui.BackColor := cBG
presetGui.SetFont("c" cTxt " s10 bold", "Segoe UI")

pt := presetGui.AddText("x0 y20 w360 h34 Center 0x200", "PRESET CONFIG")
pt.SetFont("s14 bold c" cAcc)

btnSavePreset := presetGui.AddText("x50 y70 w260 h36 Center 0x200 Background" cGrn, "SAVE TO FILE")
btnSavePreset.SetFont("s10 bold c" cSide)
btnSavePreset.OnEvent("Click", SavePresetToFile)

btnLoadPreset := presetGui.AddText("x50 y120 w260 h36 Center 0x200 Background" cAcc, "LOAD FROM FILE")
btnLoadPreset.SetFont("s10 bold c" cSide)
btnLoadPreset.OnEvent("Click", LoadPresetFromFile)

btnBackPreset := presetGui.AddText("x50 y170 w260 h36 Center 0x200 Background" cCard, "BACK TO MENU")
btnBackPreset.SetFont("s10 bold c" cTxt)
btnBackPreset.OnEvent("Click", (*) => (presetGui.Hide(), settings.Show()))

; --- Hotkey Panel ---
panel := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x20 +E0x80000 +Owner", "")
panel.BackColor := cSide
panel.SetFont("s9 c" cTxt, "Segoe UI")
WinSetTransparent(220, panel.Hwnd)

panel.AddText("x0 y0 w210 h3 Background" cAcc)
pnTitle := panel.AddText("x14 y11 w90 h22 0x200", "Zxoos")
pnTitle.SetFont("s11 bold cFFFFFF", "Segoe UI")
pnStatus := panel.AddText("x100 y11 w96 h22 0x200 Right", "ENABLED")
pnStatus.SetFont("s8 bold c9ECE6A", "Segoe UI")
panel.AddText("x14 y38 w182 h1 Background" cLine)

pnName := []
pnKey := []
loop 10 {
    nm := panel.AddText("x14 y0 w112 h20 0x200 Hidden", "")
    nm.SetFont("s9 norm c" cTxt, "Segoe UI")
    kb := panel.AddText("x130 y0 w66 h18 Center 0x200 Hidden Background" cLine, "")
    kb.SetFont("s8 bold c" cAcc, "Segoe UI")
    pnName.Push(nm)
    pnKey.Push(kb)
}
pnEmpty := panel.AddText("x14 y0 w182 h20 0x200 Hidden", "No macro enabled")
pnEmpty.SetFont("s9 italic c" cMut, "Segoe UI")
pnSep := panel.AddText("x14 y0 w182 h1 Background" cLine)
pnSysName := []
pnSysKey := []
for sysLabel in ["Toggle macros", "Exit"] {
    nm := panel.AddText("x14 y0 w112 h20 0x200", sysLabel)
    nm.SetFont("s9 norm c" cMut, "Segoe UI")
    kb := panel.AddText("x130 y0 w66 h18 Center 0x200 Background" cLine, "")
    kb.SetFont("s8 bold c" cMut, "Segoe UI")
    pnSysName.Push(nm)
    pnSysKey.Push(kb)
}
global panelH := 120

; --- Events ---
about.OnEvent("Click", infoo)
presetBtn.OnEvent("Click", OpenPresetMenu)

for c in [hotkeypanel, cordcheck, lthmacro, lthv2macro, rgcmacro]
    c.OnEvent("Click", savesettings)

for c in [robloxsensivity, hkmenuopacity, lthshiftlock, lthsleep, lthjump, lthdashstyle, lthsleep2
        , lthv2sleep, lthv2jump, lthv2dashstyle, lthv2sleep2
        , rgcdash, rgcdelay, rgchold]
    c.OnEvent("Change", savesettings)

for c in [exithk, togglehk, menutogglehk, lthhk, lthv2hk, rgchk] {
    c.OnEvent("Change", savesettings)
    c.OnEvent("Change", focused)
}
hkmenuopacity.OnEvent("Change", hkopacity)

for b in bdSet {
    b.macro.OnEvent("Click", savesettings)
    b.hk.OnEvent("Change", savesettings)
    b.hk.OnEvent("Change", focused)
    b.skill.OnEvent("Change", savesettings)
}

OnExit(CleanupKeys)

; --- Macro Definitions ---
global macros := [
    { hotkey: exithk,          function: exitmacro,     roblox: false },
    { hotkey: togglehk,        function: ToggleMacros,  roblox: false },
    { hotkey: menutogglehk,    function: menutoggle,    roblox: false },
    { hotkey: lthhk,           function: lethalv1,      roblox: true },
    { hotkey: lthv2hk,         function: lethalv2,      roblox: true },
    { hotkey: bdSet[1].hk,     function: backdash1,     roblox: true },
    { hotkey: bdSet[2].hk,     function: backdash2,     roblox: true },
    { hotkey: bdSet[3].hk,     function: backdash3,     roblox: true },
    { hotkey: bdSet[4].hk,     function: backdash4,     roblox: true },
    { hotkey: rgchk,           function: rgc,           roblox: true }
]

; --- GUI Functions ---
SelectTab(i, *) {
    global curPage
    curPage := i
    for p, arr in pages {
        for c in arr
            c.Visible := (p = i) && wantVis.Get(c.Hwnd, true)
    }
    navbar.Move(16, 82 + ((i - 1) * 36))
    for j, n in navItems {
        n.SetFont("s10 bold c" (j = i ? cTxt : cMut))
        n.Redraw()
    }
    focused()
}

SetVis(ctrl, state) {
    wantVis[ctrl.Hwnd] := state
    ctrl.Visible := state && (pageOf.Get(ctrl.Hwnd, 0) = curPage)
}

CtrlCount() {
    k := 0
    for h, c in settings
        k++
    return k
}

BeginPage(n) {
    global buildPage, pageStart
    EndPage()
    buildPage := n
    pageStart := CtrlCount()
}

EndPage() {
    global buildPage
    if (buildPage = 0)
        return
    idx := 0
    for h, c in settings {
        idx++
        if (idx > pageStart) {
            pages[buildPage].Push(c)
            pageOf[h] := buildPage
        }
    }
    buildPage := 0
}

PrettyKey(k) {
    mods := ""
    while (k != "") {
        ch := SubStr(k, 1, 1)
        if (ch = "^")
            mods .= "Ctrl+"
        else if (ch = "!")
            mods .= "Alt+"
        else if (ch = "+")
            mods .= "Shift+"
        else if (ch = "#")
            mods .= "Win+"
        else
            break
        k := SubStr(k, 2)
    }
    return StrUpper(mods k)
}

UpdatePanel() {
    global panelH
    items := [
        [lthmacro,           "Lethal V1",       lthhk],
        [lthv2macro,         "Lethal V2",       lthv2hk],
        [bdSet[1].macro,     "Backdash Slot 1", bdSet[1].hk],
        [bdSet[2].macro,     "Backdash Slot 2", bdSet[2].hk],
        [bdSet[3].macro,     "Backdash Slot 3", bdSet[3].hk],
        [bdSet[4].macro,     "Backdash Slot 4", bdSet[4].hk],
        [rgcmacro,           "RGC",             rgchk]
    ]
    y := 46
    cnt := 0
    for i, row in items {
        if (row[1].Value) {
            cnt++
            pnName[i].Value := row[2]
            pnKey[i].Value := PrettyKey(row[3].Value)
            pnName[i].Move(14, y, 112, 20)
            pnKey[i].Move(130, y + 1, 66, 18)
            pnName[i].Visible := true
            pnKey[i].Visible := true
            y += 24
        } else {
            pnName[i].Visible := false
            pnKey[i].Visible := false
        }
    }
    if (cnt = 0) {
        pnEmpty.Move(14, y, 182, 20)
        pnEmpty.Visible := true
        y += 26
    } else {
        pnEmpty.Visible := false
    }
    pnSep.Move(14, y + 4, 182, 1)
    y += 12
    pnSysName[1].Move(14, y, 112, 20)
    pnSysKey[1].Move(130, y + 1, 66, 18)
    pnSysKey[1].Value := PrettyKey(togglehk.Value)
    y += 24
    pnSysName[2].Move(14, y, 112, 20)
    pnSysKey[2].Move(130, y + 1, 66, 18)
    pnSysKey[2].Value := PrettyKey(exithk.Value)
    y += 24
    panelH := y + 8
    st()
}

ShowPanel() {
    if (!hotkeypanel.Value) {
        panel.Hide()
        return
    }
    if (cordcheck.Value) {
        if (WinActive("ahk_exe RobloxPlayerBeta.exe")) {
            WinGetPos(&wx, &wy, &ww, &wh, "ahk_exe RobloxPlayerBeta.exe")
            px := wx + 14
            py := wy + wh - panelH - 14
        } else {
            panel.Hide()
            return
        }
    } else {
        px := 14
        py := A_ScreenHeight - panelH - 80
    }
    panel.Show("NoActivate x" px " y" py " w210 h" panelH)
    WinSetRegion("0-0 W210 H" panelH " R14-14", panel.Hwnd)
}

PanelTick(*) => ShowPanel()

st(*) {
    if (macrosEnabled) {
        pnStatus.SetFont("s8 bold c9ECE6A", "Segoe UI")
        pnStatus.Value := "ENABLED"
    } else {
        pnStatus.SetFont("s8 bold cF7768E", "Segoe UI")
        pnStatus.Value := "DISABLED"
    }
}

global registeredGlobalHotkeys := []
global registeredRobloxHotkeys := []

ApplyHotkeys(*) {
    global registeredGlobalHotkeys, registeredRobloxHotkeys, macros

    HotIf()
    for key in registeredGlobalHotkeys {
        try Hotkey(key, "Off")
    }
    registeredGlobalHotkeys := []

    HotIfWinActive("ahk_exe RobloxPlayerBeta.exe")
    for key in registeredRobloxHotkeys {
        try Hotkey(key, "Off")
    }
    registeredRobloxHotkeys := []
    HotIf()

    globalMap := Map()
    robloxMap := Map()

    for macro in macros {
        key := macro.hotkey.Value
        if (key = "")
            continue

        if (macro.roblox) {
            if !robloxMap.Has(key)
                robloxMap[key] := []
            robloxMap[key].Push(macro.function)
        } else {
            if !globalMap.Has(key)
                globalMap[key] := []
            globalMap[key].Push(macro.function)
        }
    }

    HotIf()
    for key, funcs in globalMap {
        RegisterGlobalHotkey(key, MakeDispatcher(funcs))
    }

    HotIfWinActive("ahk_exe RobloxPlayerBeta.exe")
    for key, funcs in robloxMap {
        RegisterRobloxHotkey(key, MakeDispatcher(funcs))
    }
    HotIf()
}

MakeDispatcher(funcs) => (*) => RunAllMacros(funcs)

RunAllMacros(funcs) {
    for f in funcs
        f.Call()
}

RegisterGlobalHotkey(key, function) {
    global registeredGlobalHotkeys
    if (key = "")
        return
    key := "~" . key
    try {
        Hotkey(key, function, "On")
        registeredGlobalHotkeys.Push(key)
    }
}

RegisterRobloxHotkey(key, function) {
    global registeredRobloxHotkeys
    if (key = "")
        return
    key := "~" . key
    try {
        Hotkey(key, function, "On")
        registeredRobloxHotkeys.Push(key)
    }
}

exitmacro(*) => ExitApp()

CleanupKeys(*) {
    if (rgcRunning)
        Send("{d Up}{a Up}{LButton Up}")
}

ToggleMacros(*) {
    global macrosEnabled
    macrosEnabled := !macrosEnabled
    st()
}

menutoggle(*) {
    if DllCall("IsWindowVisible", "Ptr", settings.Hwnd) {
        settings.Hide()
        return
    }
    info.Hide()
    presetGui.Hide()
    settings.Show("w860 h560")
}

hkopacity(*) {
    try {
        WinSetTransparent(Min(255, Max(30, Integer(hkmenuopacity.Value))), panel.Hwnd)
    } catch {
        hkmenuopacity.Value := 220
    }
}

infoo(*) {
    settings.Hide()
    info.Show("w400 h300")
}

OpenPresetMenu(*) {
    settings.Hide()
    presetGui.Show("w360 h230")
}

dcServer(*) => Run("https://discord.gg/AEyPMqDCeN")

backk(*) {
    info.Hide()
    settings.Show("w860 h560")
    focused()
}

calculator(*) {
    val := robloxsensivity.Value
    sens := (IsNumber(val) && Float(val) > 0) ? Float(val) : 0.4

    global r1 := 360, r2 := -360, r6 := 350, r7 := -101.2, r8 := -102.4, r9 := 36, r10 := 38.8
    global L1 := r1 / sens
    global L3 := r6 / sens
    global L4 := r7 / sens
    global S1 := r8 / sens
    global S2 := r9 / sens
    global S3 := r10 / sens
}

savesettings(*) {
    SetTimer(PanelTick, 0)
    calculator()
    ApplyHotkeys()
    UpdatePanel()

    if (lthv2dashstyle.Text = "1") {
        SetVis(lthv2text, false)
        SetVis(lthv2sleep2, false)
        lthv2sleep.Enabled := true
    } else if (lthv2dashstyle.Text = "2") {
        SetVis(lthv2text, true)
        SetVis(lthv2sleep2, true)
        lthv2sleep.Enabled := false
    }

    if (lthshiftlock.Text = "Shiftlock") {
        SetVis(lthtext2, true)
        SetVis(lthdashstyle, true)
        if (lthdashstyle.Text = "1") {
            SetVis(lthsleep2, false)
            SetVis(lthtext, false)
            lthsleep.Enabled := true
        } else if (lthdashstyle.Text = "2") {
            SetVis(lthsleep2, true)
            SetVis(lthtext, true)
            lthsleep.Enabled := false
        }
    } else if (lthshiftlock.Text = "Unshiftlock") {
        SetVis(lthsleep2, false)
        SetVis(lthtext, false)
        SetVis(lthdashstyle, false)
        SetVis(lthtext2, false)
        lthsleep.Enabled := false
    }

    ShowPanel()
    if (hotkeypanel.Value && cordcheck.Value)
        SetTimer(PanelTick, 100)
}

focused(*) {
    SendMessage(0x0128, (1 | (1 << 16)), 0, settings.Hwnd)
    ControlFocus(settings.Hwnd)
}

preciseSleep(ms) {
    static freq := 0
    if (!freq)
        DllCall("QueryPerformanceFrequency", "Int64*", &freq)
    DllCall("QueryPerformanceCounter", "Int64*", &start := 0)
    target := start + (ms * freq / 1000)
    current := 0
    while (current < target)
        DllCall("QueryPerformanceCounter", "Int64*", &current)
}

SavePresetToFile(*) {
    filePath := FileSelect("S16", "config.ini", "Save Preset File", "INI Config (*.ini)")
    if (filePath = "")
        return

    IniWrite(robloxsensivity.Value, filePath, "General", "Sensitivity")
    IniWrite(exithk.Value, filePath, "General", "ExitHK")
    IniWrite(togglehk.Value, filePath, "General", "ToggleHK")
    IniWrite(menutogglehk.Value, filePath, "General", "MenuToggleHK")
    IniWrite(hkmenuopacity.Value, filePath, "General", "Opacity")
    IniWrite(hotkeypanel.Value, filePath, "General", "HotkeyPanel")
    IniWrite(cordcheck.Value, filePath, "General", "CoordCheck")

    IniWrite(lthmacro.Value, filePath, "Lethal", "V1")
    IniWrite(lthhk.Value, filePath, "Lethal", "V1HK")
    IniWrite(lthshiftlock.Value, filePath, "Lethal", "V1Shiftlock")
    IniWrite(lthsleep.Value, filePath, "Lethal", "V1Sleep")
    IniWrite(lthjump.Value, filePath, "Lethal", "V1Jump")
    IniWrite(lthdashstyle.Value, filePath, "Lethal", "V1DashStyle")
    IniWrite(lthsleep2.Value, filePath, "Lethal", "V1Sleep2")

    IniWrite(lthv2macro.Value, filePath, "Lethal", "V2")
    IniWrite(lthv2hk.Value, filePath, "Lethal", "V2HK")
    IniWrite(lthv2sleep.Value, filePath, "Lethal", "V2Sleep")
    IniWrite(lthv2jump.Value, filePath, "Lethal", "V2Jump")
    IniWrite(lthv2dashstyle.Value, filePath, "Lethal", "V2DashStyle")
    IniWrite(lthv2sleep2.Value, filePath, "Lethal", "V2Sleep2")

    for i, b in bdSet {
        IniWrite(b.macro.Value, filePath, "Backdash", "Macro" i)
        IniWrite(b.hk.Value, filePath, "Backdash", "HK" i)
        IniWrite(b.skill.Value, filePath, "Backdash", "Skill" i)
    }

    IniWrite(rgcmacro.Value, filePath, "RGC", "Macro")
    IniWrite(rgchk.Value, filePath, "RGC", "HK")
    IniWrite(rgcdash.Value, filePath, "RGC", "Dash")
    IniWrite(rgcdelay.Value, filePath, "RGC", "Delay")
    IniWrite(rgchold.Value, filePath, "RGC", "Hold")

    MsgBox("Preset berhasil disimpan!", "Sukses", "0x40")
}

LoadPresetFromFile(*) {
    filePath := FileSelect("3",, "Select Preset File", "INI Config (*.ini)")
    if (filePath = "" || !FileExist(filePath))
        return

    try {
        robloxsensivity.Value := IniRead(filePath, "General", "Sensitivity", "0.4")
        exithk.Value := IniRead(filePath, "General", "ExitHK", "F1")
        togglehk.Value := IniRead(filePath, "General", "ToggleHK", "F2")
        menutogglehk.Value := IniRead(filePath, "General", "MenuToggleHK", "F3")
        hkmenuopacity.Value := IniRead(filePath, "General", "Opacity", "220")
        hotkeypanel.Value := Integer(IniRead(filePath, "General", "HotkeyPanel", "0"))
        cordcheck.Value := Integer(IniRead(filePath, "General", "CoordCheck", "0"))

        lthmacro.Value := Integer(IniRead(filePath, "Lethal", "V1", "0"))
        lthhk.Value := IniRead(filePath, "Lethal", "V1HK", "r")
        lthshiftlock.Text := IniRead(filePath, "Lethal", "V1Shiftlock", "Shiftlock")
        lthsleep.Value := IniRead(filePath, "Lethal", "V1Sleep", "220")
        lthjump.Text := IniRead(filePath, "Lethal", "V1Jump", "On")
        lthdashstyle.Text := IniRead(filePath, "Lethal", "V1DashStyle", "1")
        lthsleep2.Value := IniRead(filePath, "Lethal", "V1Sleep2", "200")

        lthv2macro.Value := Integer(IniRead(filePath, "Lethal", "V2", "0"))
        lthv2hk.Value := IniRead(filePath, "Lethal", "V2HK", "r")
        lthv2sleep.Value := IniRead(filePath, "Lethal", "V2Sleep", "190")
        lthv2jump.Text := IniRead(filePath, "Lethal", "V2Jump", "On")
        lthv2dashstyle.Text := IniRead(filePath, "Lethal", "V2DashStyle", "1")
        lthv2sleep2.Value := IniRead(filePath, "Lethal", "V2Sleep2", "75")

        for i, b in bdSet {
            b.macro.Value := Integer(IniRead(filePath, "Backdash", "Macro" i, "0"))
            b.hk.Value := IniRead(filePath, "Backdash", "HK" i, "z")
            b.skill.Value := IniRead(filePath, "Backdash", "Skill" i, String(i))
        }

        rgcmacro.Value := Integer(IniRead(filePath, "RGC", "Macro", "0"))
        rgchk.Value := IniRead(filePath, "RGC", "HK", "g")
        rgcdash.Text := IniRead(filePath, "RGC", "Dash", "Right")
        rgcdelay.Value := IniRead(filePath, "RGC", "Delay", "10")
        rgchold.Text := IniRead(filePath, "RGC", "Hold", "On")

        savesettings()
        MsgBox("Preset berhasil dimuat!", "Sukses", "0x40")
    } catch {
        MsgBox("Gagal memuat preset! Pastikan file valid.", "Error", "0x10")
    }
}

lethalv1(*) {
    if (!lthmacro.Value || !macrosEnabled)
        return
    if (lthshiftlock.Text = "Shiftlock") {
        if (lthjump.Text = "On") {
            if (lthdashstyle.Text = "1") {
                Send("{q}")
                Send("{Space Down}")
                PreciseSleep(Integer(lthsleep.Value))
                DllCall("mouse_event", "UInt", 1, "Int", L1, "Int", 0)
                Send("{Space Up}")
                return
            }
            if (lthdashstyle.Text = "2") {
                Send("{q}")
                Send("{Space Down}")
                PreciseSleep(Integer(lthsleep2.Value))
                loop 4 {
                    DllCall("mouse_event", "UInt", 1, "Int", L4, "Int", 0)
                    PreciseSleep(15)
                }
                Send("{Space Up}")
                return
            }
        }
        if (lthjump.Text = "Off") {
            if (lthdashstyle.Text = "1") {
                Send("{q}")
                PreciseSleep(Integer(lthsleep.Value))
                DllCall("mouse_event", "UInt", 1, "Int", L1, "Int", 0)
                return
            }
            if (lthdashstyle.Text = "2") {
                Send("{q}")
                PreciseSleep(Integer(lthsleep2.Value))
                loop 4 {
                    DllCall("mouse_event", "UInt", 1, "Int", L4, "Int", 0)
                    PreciseSleep(15)
                }
                return
            }
        }
    } else {
        if (lthjump.Text = "On") {
            Send("{q}")
            Send("{Space Down}")
            PreciseSleep(Integer(lthsleep.Value))
            Send("{Shift}")
            Send("{Space Up}")
        }
        if (lthjump.Text = "Off") {
            Send("{q}")
            PreciseSleep(Integer(lthsleep.Value))
            Send("{Shift}")
        }
    }
}

lethalv2(*) {
    if (!lthv2macro.Value || !macrosEnabled)
        return
    if (lthv2jump.Text = "Off" && lthv2dashstyle.Text = "1") {
        DllCall("mouse_event", "UInt", 1, "Int", L1, "Int", 0)
        Send("{q}")
        PreciseSleep(Integer(lthv2sleep.Value))
        DllCall("mouse_event", "UInt", 1, "Int", L3, "Int", 0)
        return
    }
    if (lthv2jump.Text = "On" && lthv2dashstyle.Text = "1") {
        DllCall("mouse_event", "UInt", 1, "Int", L1, "Int", 0)
        Send("{Space Down}")
        Send("{q}")
        PreciseSleep(Integer(lthv2sleep.Value))
        DllCall("mouse_event", "UInt", 1, "Int", L3, "Int", 0)
        Send("{Space Up}")
        return
    }
    if (lthv2jump.Text = "On" && lthv2dashstyle.Text = "2") {
        Send("{Space Down}")
        Send("{q}")
        PreciseSleep(30)
        Loop 10 {
            DllCall("mouse_event", "UInt", 1, "Int", S2, "Int", 0)
            PreciseSleep(8)
        }
        PreciseSleep(70)
        Loop 10 {
            DllCall("mouse_event", "UInt", 1, "Int", S3, "Int", 0)
            PreciseSleep(5)
        }
        Send("{Space Up}")
        return
    }
    if (lthv2jump.Text = "Off" && lthv2dashstyle.Text = "2") {
        Send("{q}")
        PreciseSleep(30)
        Loop 10 {
            DllCall("mouse_event", "UInt", 1, "Int", S2, "Int", 0)
            PreciseSleep(8)
        }
        PreciseSleep(70)
        Loop 10 {
            DllCall("mouse_event", "UInt", 1, "Int", S3, "Int", 0)
            PreciseSleep(5)
        }
        return
    }
}

RunBD(n) {
    b := bdSet[n]
    if (!b.macro.Value || !macrosEnabled)
        return
    skillKey := b.skill.Value
    if (skillKey = "")
        skillKey := n

    SendEvent("{" skillKey " down}{s down}{q down}")
    PreciseSleep(16)
    SendEvent("{" skillKey " up}{s up}{q up}")
}
backdash1(*) => RunBD(1)
backdash2(*) => RunBD(2)
backdash3(*) => RunBD(3)
backdash4(*) => RunBD(4)

rgc(*) {
    global rgcRunning
    if (!rgcmacro.Value || !macrosEnabled || rgcRunning)
        return
    key := RegExReplace(rgchk.Value, "^[\^!+#<>*~$]+")
    if (key = "")
        return
    dashKey := (rgcdash.Text = "Right") ? "d" : "a"
    delay := (rgcdelay.Value = "") ? 10 : Max(1, Integer(rgcdelay.Value))
    holdM1 := (rgchold.Text = "On")

    rgcRunning := true
    if (holdM1)
        Send("{LButton Down}")
    Send("{" dashKey " Down}")
    while (GetKeyState(key, "P") && macrosEnabled) {
        Send("{q}")
        PreciseSleep(delay)
    }
    Send("{" dashKey " Up}")
    if (holdM1)
        Send("{LButton Up}")
    rgcRunning := false
}

settings.Show("w860 h560")
savesettings()
SelectTab(1)