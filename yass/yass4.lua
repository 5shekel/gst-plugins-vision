--[[
Yet Another Sunset Script v4.8
@title yass 4.8
@chdk_version 1.3
  -- Based on scripts by Fbonomi and soulf2
  -- Released under GPL by waterwingz
@param     t Shot Rate (sec)
  @default t 10
  @range   t 1 3600
@param     o Compensation (f-stops)
  @default o 8
  @values  o -4.0 -3.5 -3.0 -2.5 -2.0 -1.5 -1.0 -0.5 0.0 0.5 1.0 1.5 2.0 2.5 3.0 3.5 4.0
@param     e Tv normal limit (sec)
  @default e 9
  @values  e Off 2.0 1.6 1.3 1.0 0.8 0.6 0.5 0.4 0.3 1/4 1/5 1/6 1/8 1/10 1/13 1/15
@param     b Tv low limit (sec)
  @default b 5
  @values  b 32 25 20 16 12 10 8.0 6.0 5.0 4.0 3.2 2.5 2.0 1.6 1.3 1.0
@param     c ISO default
  @default c 1
  @values  c 80 100 125 160 200 250 320 400 500 640 800 1250 1600
@param     d ISO upper limit
  @default d 7
  @values  d 80 100 125 160 200 250 320 400 500 640 800 1250 1600
@param     f Exposure ramp rate
  @default f 2
  @values  f VSlow Slow Medium Fast VFast
@param     a Aperture Setting
  @default a 0
  @values  a min_Av f1.8 f2.0 f2.8 f3.2 f4.0 f5.6 f6.3 f8 f11 f16
@param     m First Shot Delay (min)
  @default m 0
  @range   m 0 240
@param     z Zoom step position
  @default z -1
  @range   z -1 100
@param     w Use ND Filter?
  @default w 1
  @range   w 0 1
@param     x Focus @ Infinity Mode
  @default x 0
  @values  x None AFL MF
@param     r RAW enable?
  @default r 0
  @range   r 0 1
@param     h Free Disk MB Shut down
  @default h 15
  @range   h 10 100
@param     y Status LED
  @default y 2
  @values  y Off 0 1 2 3 4 5 6 7 8
@param     n Display blanking mode
  @default n 0
  @values  n None BKLite DispKey ShrtCut
@param     l Logging
  @default l 2
  @values  l Off Screen SDCard Both
--]]

props=require("propcase")

tv_ref = {    -- note : tv_ref values set 1/2 way between shutter speed values
-608, -560, -528, -496, -464, -432, -400, -368, -336, -304,
-272, -240, -208, -176, -144, -112,  -80,  -48,  -16,   16,
  48,   80,  112,  144,  176,  208,  240,  272,  304,  336,
 368,  400,  432,  464,  496,  528,  560,  592,  624,  656,
 688,  720,  752,  784,  816,  848,  880,  912,  944,  976,
1008, 1040, 1072, 1096, 1129, 1169, 1192, 1225, 1265, 1376  }
av_ref = {176,208,240,272,304,336,368,400,432,464,496,512,528,560,592,624,656,688,720,752}
sv_ref = {378,420,440,462,486,531,576,612,645,678,709,739,772,805}

-- translate user parameter into usable values & names
    interval = t*1000
    if (e >0) then tv_normal_limit = tv_ref[e+15] else tv_normal_limit = 1192 end
    tv96_low_limit = tv_ref[b+4]
    apex96_ramp_rate =(f+1) * math.min(1+(t/8),10)
    sv96_default = sv_ref[c+1]
    sv96_max = sv_ref[d+1]
    av_table = {0, 171,192,288,320,384,480,512,576,672,768}
    av96 = av_table[a+1]
    zoom_setpoint = z
    focus_mode = x
    min_disk_space = h*1024
    compensation = (o-8)*48
    nd_filter = w
    log_mode = l
    display_mode = n
    status_led = y-1

-- constants
    nd96=288                -- ND filter's number of equivalent f-stops
    nd_tv_limit = 960       -- engage ND filter if tv < 1/1000 sec
    SHORTCUT="print"        -- edit this if using shortcut key to enter sleep mode

-- camera configuration
    shot=1
    done=0
    timestamp=0
    led_state = 0
    led_timer = 10
    display_state = 1
    display_hold_timer = 0
     
function restore()
    set_backlight(1)
    set_led(status_led,0)
    set_raw(original_raw)
    unlock_focus()
end

function update_zoom()
    local count = 0
    zsteps=get_zoom_steps()
    if(zoom_setpoint>zsteps) then zoom_setpoint=zsteps end
    print("setting zoom to step",zoom_setpoint,"of",zsteps)
    sleep(2000)
    set_zoom(zoom_setpoint)
    sleep(2000)
    press("shoot_half")
    repeat
        sleep(100)
        count = count + 1
    until (get_shooting() == true ) or (count > 40 )   
    release("shoot_half")
end

-- focus lock and unlock
function lock_focus()
    if (focus_mode > 0) then                                            -- focus mode requested ?
        if     ( focus_mode == 1 ) then                                 -- method 1 :  set_aflock() command enables MF
            if (chdk_version==120) then
                set_aflock(1)
                set_prop(props.AF_LOCK,1)
            else
                set_aflock(1)
            end
            if (get_prop(props.AF_LOCK) == 1) then print(" AFL enabled") else print(" AFL failed ***") end
        else                                                            -- mf mode requested
            if (chdk_version==120) then                                 -- CHDK 1.2.0 : call event proc or levents to try and enable MF mode
                if call_event_proc("SS.Create") ~= -1 then
                    if call_event_proc("SS.MFOn") == -1 then
                            call_event_proc("PT_MFOn")
                    end
                elseif call_event_proc("RegisterShootSeqEvent") ~= -1 then
                    if call_event_proc("PT_MFOn") == -1 then
                        call_event_proc("MFOn")
                    end
                end
                if (get_prop(props.FOCUS_MODE) == 0 ) then              -- MF not set - try levent PressSw1AndMF
                    post_levent_for_npt("PressSw1AndMF")
                    sleep(500)
                end
            elseif (chdk_version >= 130) then                           -- CHDK 1.3.0 : set_mf()
                if ( set_mf(1) == 0 ) then set_aflock(1) end            --    as a fall back, try setting AFL is set_mf fails
            end
            if (get_prop(props.FOCUS_MODE) == 1) then print(" MF enabled") else print(" MF enable failed ***") end
        end
        sleep(1000)
        if(set_focus(50000)==0) then print("infinity focus error") end
        sleep(1000)
    end
end

function unlock_focus()
    if (focus_mode > 0) then                                            -- focus mode requested ?
        if (focus_mode == 1 ) then                                      -- method 1 : AFL
            if (chdk_version==120) then
                set_aflock(0)
                set_prop(props.AF_LOCK,0)
            else
                set_aflock(0)
            end
            if (get_prop(props.AF_LOCK) == 0) then print("AFL unlocked") else print("AFL unlock failed") end
         else                                                           -- mf mode requested
             if (chdk_version==120) then                                -- CHDK 1.2.0 : call event proc or levents to try and enable MF mode
                if call_event_proc("SS.Create") ~= -1 then
                    if call_event_proc("SS.MFOff") == -1 then
                        call_event_proc("PT_MFOff")
                    end
                elseif call_event_proc("RegisterShootSeqEvent") ~= -1 then
                    if call_event_proc("PT_MFOff") == -1 then
                        call_event_proc("MFOff")
                    end
                end
                if (get_prop(props.FOCUS_MODE) == 1 ) then              -- MF not reset - try levent PressSw1AndMF
                    post_levent_for_npt("PressSw1AndMF")
                    sleep(500)
                end
            elseif (chdk_version >= 130) then                           -- CHDK 1.3.0 : set_mf()
                if ( set_mf(0) == 0 ) then set_aflock(0) end            --    fall back so reset AFL is set_mf fails
            end
            if (get_prop(props.FOCUS_MODE) == 0) then print("MF disabled") else print("MF disable failed") end
        end
        sleep(100)
    end
end

function print_tv(val)
    local i = 1
    local tv_str = {
       ">64",
        "64",    "50",    "40",   "32",   "25",   "20",   "16",   "12",    "10",   "8.0",
       "6.0",   "5.0",   "4.0",  "3.2",  "2.5",  "2.0",  "1.6",  "1.3",   "1.0",   "0.8",
       "0.6",   "0.5",   "0.4",  "0.3",  "1/4",  "1/5",  "1/6",  "1/8",  "1/10",  "1/13",
      "1/15",  "1/20",  "1/25", "1/30", "1/40", "1/50", "1/60", "1/80", "1/100", "1/125",
     "1/160", "1/200", "1/250","1/320","1/400","1/500","1/640","1/800","1/1000","1/1250",
    "1/1600","1/2000","1/2500","1/3200","1/4000","1/5000","1/6400","1/8000","1/10000","hi"  }
    while (i <= #tv_ref) and (val > tv_ref[i]-1) do i=i+1 end
    return tv_str[i]
end

function print_av(val)
    local i = 1
    local av_str = {"n/a","2.0","2.2","2.5","2.8","3.2","3.5","4.0","4.5","5.0",
                    "5.6","5.9","6.3","7.1","8.0","9.0","10.0","11.0","13.0","14.0","16.0"}
    while (i <= #av_ref) and (val > av_ref[i]-1) do i=i+1 end
    return av_str[i]
end

function print_sv(val)
    local i = 1
    local sv_str = {"n/a","80","100","125","160","200","250","320","400","500","640","800","1250","1600","3200"}
    while (i <= #sv_ref) and (val > sv_ref[i]-1) do i=i+1 end
    return sv_str[i]
end

function sd_log(logmsg)
    if ( log_mode > 1 ) then
        local logname="A/yass4.csv"   
        retry = 0
        repeat
            log=io.open(logname,"a")           
            if ( log~=nil) then 
                log:write(os.date(s,tm),": ",logmsg,"\n") 
                log:close()
                return
            end
            sleep(250) 
            retry = retry+1
        until(retry > 7)
        print("Error : log file open fault!") 
    end
end
 
function lprint(logmsg)
    if ( log_mode > 0) then
        if (( log_mode == 1) or (log_mode == 3)) then print(logmsg) end
        sd_log(logmsg)
    end
end

function sleep_mode(m)     --  press user shortcut key to toggle sleep mode
    press(SHORTCUT)
    sleep(1000)
    release(SHORTCUT)
    sleep(500)
end


function set_display_key(m)  -- click display key to get to desire LCD display mode 0=off, 1=on
    if (m==0) then m=2 else m=0 end
    local count=5
    local clicks=0
    sleep(200)
    repeat
        disp = get_prop(props.DISPLAY_MODE)
        if ( disp ~= m ) then
            click("display")
            clicks=clicks+1
            sleep(500)
        end
        count=count-1
    until (( disp==m ) or (count==0))
    if (clicks>0 and count==0) then
        print("unable to change display")
    end
end

function set_display(m)   --   m=0 for turn off display, m>0 turn on for m seconds
    if (display_mode>0) then
        if ( display_hold_timer>0) then
            if (m>1) then display_hold_timer = display_hold_timer+m end
    else
            if (m>1) then
                display_hold_timer = m
                m=1
            end
            local st="off"
            if (m>0) then st="on" end
            if ( display_mode==1) then
                if (display_state ~= m) then print("set backlight "..st) end
                sleep(1000)
                set_backlight(m)
            elseif ( display_mode==2) then
                if( display_state ~= m) then 
                    print("set display "..st)
                    set_display_key(m)
                    if ( focus_mode > 0 ) then
                       lock_focus()
                    end
                 end
            elseif ( display_mode==3) then
                if (display_state ~= m) then
                    print("toggle sleep mode")
                    sleep_mode(m)
               end
            end
            display_state=m
        end
    end
end

--[[ ========================== Main Program ================================= --]]

set_console_layout(2, 0, 44, 10)
print("Yet Another Sunset Script V4.8")

bi=get_buildinfo()
chdk_version= tonumber(string.sub(bi.build_number,1,1))*100 + tonumber(string.sub(bi.build_number,3,3))*10 + tonumber(string.sub(bi.build_number,5,5))
if ( tonumber(bi.build_revision) > 0 ) then
    build = tonumber(bi.build_revision)
else
    build = tonumber(string.match(bi.build_number,'-(%d+)$'))
end

if (chdk_version<120) then
    printf("CHDK 1.2.0 or higher required")
elseif((chdk_version==120)and(build<3276)) then
    printf("CHDK 1.2.0 build 3276 or higher required")
elseif((chdk_version==130)and(build<3383)) then    
    printf("CHDK 1.3.0 build 3383 or higher required")
else
    print("CHDK version okay")
    lprint(" tvl="..print_tv(tv96_low_limit).." tvh="..print_tv(tv_normal_limit).." ISOd="..print_sv(sv96_default).." ISOm="..print_sv(sv96_max))
    lprint(" shot rate="..(interval/1000).." ramp:"..apex96_ramp_rate)
    sleep(200)

-- setup - disable flash, image stabilization and AF assist lamp
    original_raw = get_raw()
    set_raw(r)
    set_prop(props.FLASH_MODE, 2)     -- flash off
    set_prop(props.IS_MODE, 3)        -- IS_MODE off
    set_prop(props.AF_ASSIST_BEAM,0)  -- AF assist off if supported for this camera

-- startup delay ?
    if ( m>0 ) then
        lprint("delaying startup for",m,"minutes")
        sleep(10)
        set_display(0)
        sleep(m*60000)
    end

-- switch to shooting mode if necessary
    if ( get_mode() == false ) then
        set_record(1)
        while ( get_mode() == false ) do sleep(100) end
    end

-- set zoom position
   if ( zoom_setpoint > -1 ) then update_zoom() end

-- lock focus at infinity ?
    lock_focus()

-- set initial shooting values (values are with ND filter out)
    press("shoot_half")
    repeat  sleep(50)  until get_shooting() == true
    release("shoot_half")
    repeat  sleep(50)  until get_shooting() == false
    sleep(100)
    dof=get_dofinfo()
    if ((dof.focus == -1) or (dof.focus>20000)) then
        print(" focus is at infinity")
    elseif ( dof.focus>dof.hyp_dist ) then
        print(" focus is past hyperfocal")
    else
        print(" focus is at "..dof.focus.." mm")
    end
    if (av96 == 0) then    -- are we in min_AV mode ?
        av96 = get_prop(props.MIN_AV)
    end
    sv96 = sv96_default

-- put titles into log file
    sd_log("YASS 4.3 "..os.date(s,tm))
    sd_log("Shot,Image,Compensation,Tv_target,Tv,Tv+,ND,ISO_target,ISO,f-stop,focus,Tv96,Sv96,Av96,Bv96")
    sleep(2000)
    
-- initialize timers
    ticsec = 0
    ticmin = 0
    set_display(20)
    set_console_layout(2, 0, 44, 3)
    print("started")
    
-- loop here until a key is pressed - exit if its the Menu key, else enable the display for 20 seconds
    repeat
        repeat
            now = get_tick_count()
            if ( now > timestamp + interval ) then
                timestamp=get_tick_count()
                if ( interval > 5000 ) then                       -- check if in slow mode
                     press("shoot_half")                          -- get current exposure readings
                     repeat  sleep(50)  until get_shooting() == true
                     release("shoot_half")
                     repeat  sleep(50)  until get_shooting() == false
                end
                bv96=get_bv96()
                bv96c=bv96-compensation                     -- calulate compensated exposure needed
                tv96needed=sv96_default+bv96c-av96          -- calculate desired shutter speed at default ISO
                if (tv96==nil) then tv96=tv96needed end
                if ( compensation >= 0 ) then
                    compstr = "+"..compensation
                else
                    compstr = "-"..compensation
                end
                if(tv96needed>tv_normal_limit) then
                    tv96=(tv96+tv96needed)/2                   -- use that shutter speed if above Tv normal limit
                    sv96=sv96_default                          -- use default ISO
                    sv96needed=sv96_default                    -- 
                else
                    if( tv96 > tv96needed) then
                        tv96=math.max(tv96-apex96_ramp_rate,tv96needed)  -- lower the shutter speed at the APEX ramp rate
                    else
                        tv96=math.min(tv96+apex96_ramp_rate,tv96needed) -- increase the shutter speed at the APEX ramp rate
                    end
                    
                    if (tv96>tv96_low_limit) then
                        sv96=sv96_default                     -- use default ISO value while Tv above lower limit
                        sv96needed=sv96_default               -- 
                    else
                        tv96=tv96_low_limit                   -- if Tv at low limit then recalculate ISO value
                        sv96needed=tv96+av96-bv96c
                        if (sv96needed>sv96_max) then
                            sv96needed=sv96_max               -- clamp ISO at high limit
                        end
                        if( sv96 > sv96needed) then
                            sv96=math.max(sv96-apex96_ramp_rate,sv96needed) -- lower the ISO at the APEX ramp rate
                        else
                            sv96=math.min(sv96+apex96_ramp_rate,sv96needed) -- increase the ISO at the APEX ramp rate
                        end
                    end
                end
                if (nd_filter==1) then
                    if (tv96 > nd_tv_limit ) then
                        tv96m = tv96-nd96
                        set_nd_filter(1)                        -- activate the ND filter
                        nd_string=" ["..print_tv(tv96m).."+NDin] "
                        nd_state=1
                    else
                        tv96m = tv96
                        set_nd_filter(2)                        -- make sure the ND filter does not activate
                        nd_string=" [NDout] "
                        nd_state=0
                    end
                else
                    tv96m = tv96
                    set_nd_filter(2)                             -- make sure the nd filter does not activate
                    nd_string=" "
                    nd_state=0
                end
                set_sv96(sv96)
                set_av96_direct(av96)
                set_tv96_direct(tv96m)
                shoot()
                if ( interval > 5000 ) then                       -- check if in slow mode
                    sleep(500)
                    local dof=get_dofinfo()
                    local imgname=string.format('IMG_%04d.JPG',get_exp_count())
                    sd_log(shot..","..imgname..","..compstr..","..print_tv(tv96needed)..","..print_tv(tv96)..","..print_tv(tv96m)..","..nd_state..","
                         .. print_sv(sv96needed)..","..print_sv(sv96)..","..print_av(av96)..","..dof.focus..","..get_tv96()..","..get_sv96()..","..get_av96()..","..get_bv96()..",")
                end
                print(shot.." Bv:"..bv96..compstr.." Tv*:"..print_tv(tv96needed).." Tv:"..print_tv(tv96)..nd_string.."ISO"..print_sv(sv96))
                shot=shot+1
                if ( display_mode ~=2 ) then display_state = 1 end  -- shooting re-enables backlight and exits sleep mode (if used)
                set_display(0)
            end

        -- process things that happen once every 15 seconds
            if ( now > ticmin ) then
                ticmin = now+15000
                set_display(0)
                collectgarbage()
            end

        -- process things that happen once per second
            if ( now > ticsec ) then
                ticsec = now+1000
                if( display_hold_timer>0) then display_hold_timer=display_hold_timer-1 end
            end

        -- status LED
            led_timer = led_timer -1
            if (led_timer == 1) then
                set_led(status_led,1)
            elseif (led_timer == 0) then
                set_led(status_led,0)
                led_timer = 20
            end

        -- check for user input
            wait_click(100)
        until not( is_key("no_key"))
        print("key pressed")
        set_display(20)
    until ( is_key("menu") or ( get_free_disk_space() < min_disk_space))

    if ( get_free_disk_space() < min_disk_space) then
        print("SD card full")
    else
        print("menu key exit")
    end
    restore()
end
