-- IWRAM 글리프 덤프 스크립트
-- 원본 ROM(패치 없는)으로 실행: 텍스트 화면에서 A 누르면 덤프
-- 038AC 함수 리턴 시 r0, r1 값과 IWRAM 내용 캡처

local IWRAM_BASE = 0x03003320
local dumped = false
local hook_set = false
local r0_val, r1_val = 0, 0

-- 038AC 함수 리턴 직전(038F8: BX r1) 시점 후킹
-- 원본 ROM에서 실행할 것: 훅 주소는 0x080038F8
callbacks:add("frame", function()
    if dumped then return end

    -- 텍스트가 표시되는 시점을 기다림 (아무 키나 누르면 덤프)
    local keys = input.read()
    if keys["A"] and not hook_set then
        hook_set = true
        print("A 감지: 다음 038AC 호출 시 덤프 예정")

        -- 038AC 함수 리턴 지점(038F8) 직후를 watchpoint로
        -- 실제로는 메모리 watchpoint 대신 execution hook 사용
        callbacks:add("exec", 0x080038F9, function()
            if dumped then return end
            dumped = true

            -- 레지스터 읽기 (mGBA Lua에서는 직접 불가, IWRAM 내용만 읽음)
            print("=== 038AC 실행 감지 @ 038F8 ===")

            -- IWRAM 글리프 영역 덤프 (0x03003320 ~ 0x03003520, 512 bytes)
            print(string.format("IWRAM @ 0x%08X 덤프:", IWRAM_BASE))
            local data = {}
            for i = 0, 511 do
                data[i+1] = memory.read8(IWRAM_BASE + i)
            end

            -- 첫 번째 글리프 (32 bytes) ASCII 아트 출력
            print("첫 글리프 (32 bytes, 16행 x 2byte/행):")
            for row = 0, 15 do
                local b0 = data[row*2 + 1]
                local b1 = data[row*2 + 2]
                local line = string.format("row%02d: %02X %02X  ", row, b0, b1)
                -- MSB-first 비트 해석
                for bit = 7, 0, -1 do
                    line = line .. (((b0 >> bit) & 1 == 1) and "#" or ".")
                end
                line = line .. " "
                for bit = 7, 0, -1 do
                    line = line .. (((b1 >> bit) & 1 == 1) and "#" or ".")
                end
                print(line)
            end

            -- 파일로 저장
            local f = io.open("D:/Works/zoe/iwram_glyph_dump.bin", "wb")
            if f then
                for i = 1, 512 do
                    f:write(string.char(data[i]))
                end
                f:close()
                print("저장: iwram_glyph_dump.bin (512 bytes)")
            end

            -- BG 맵도 덤프해서 어떤 tile index가 사용되는지 확인
            local bgmap_base = 0x06000000
            local bgmap = {}
            for i = 0, 0x7FF do  -- 첫 2KB BG맵
                bgmap[i+1] = memory.read16(bgmap_base + i*2)
            end
            print("BG맵 첫 32 entries (tile indices):")
            local bline = ""
            for i = 1, 32 do
                bline = bline .. string.format("%04X ", bgmap[i])
            end
            print(bline)

            -- DISPCNT / BG0CNT 확인
            local dispcnt = memory.read16(0x04000000)
            local bg0cnt  = memory.read16(0x04000008)
            local bg1cnt  = memory.read16(0x0400000A)
            print(string.format("DISPCNT=%04X BG0CNT=%04X BG1CNT=%04X", dispcnt, bg0cnt, bg1cnt))
        end)
    end
end)

print("dump_glyph.lua 로드됨")
print("원본(패치 없는) ROM으로 실행하세요")
print("텍스트 화면에서 A버튼을 누르면 덤프됩니다")
