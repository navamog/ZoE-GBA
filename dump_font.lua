-- mGBA Lua script: VRAM 타일 데이터 덤프
local frameCount = 0
local dumped = false

-- 300프레임 후 (약 5초) VRAM 덤프
callbacks:add("frame", function()
    frameCount = frameCount + 1

    -- A버튼 계속 누르기 (인트로 스킵)
    if frameCount % 60 < 30 then
        joypad.set({A=true})
    else
        joypad.set({A=false})
    end

    if frameCount == 600 and not dumped then
        dumped = true
        print("Dumping VRAM tiles...")

        -- VRAM 타일셋 4개 덤프 (0x06000000 ~ 0x06010000)
        local file = io.open("D:/Works/zoe/vram_tiles.bin", "wb")
        if file then
            for i = 0, 0xFFFF do
                local b = memory.read8(0x06000000 + i)
                file:write(string.char(b))
            end
            file:close()
            print("VRAM tiles dumped to vram_tiles.bin")
        end

        -- BG 맵 데이터도 덤프
        local mapfile = io.open("D:/Works/zoe/vram_map.bin", "wb")
        if mapfile then
            -- BG Map: 0x06010000 ~ 0x06020000
            for i = 0, 0xFFFF do
                local b = memory.read8(0x06010000 + i)
                mapfile:write(string.char(b))
            end
            mapfile:close()
            print("BG Map dumped to vram_map.bin")
        end

        -- DISPCNT 레지스터 (디스플레이 설정 확인)
        local dispcnt = memory.read16(0x04000000)
        print(string.format("DISPCNT: 0x%04X (Mode=%d)", dispcnt, dispcnt & 7))

        -- BG0 제어
        local bg0cnt = memory.read16(0x04000008)
        print(string.format("BG0CNT: 0x%04X", bg0cnt))
        local bg1cnt = memory.read16(0x0400000A)
        print(string.format("BG1CNT: 0x%04X", bg1cnt))

        print("Done! Closing...")
        -- 게임 종료
        emu.exit()
    end
end)

print("Font dump script loaded. Waiting 600 frames...")
