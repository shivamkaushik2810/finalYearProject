-- 07_timetable_edit_tests.sql
-- Tests for apply_timetable_change. Test rows are created inside this one statement.
-- The final RAISE EXCEPTION rolls the whole statement back, so nothing is saved.
-- Read the PASS / FAIL lines in the error message.

do $test$
declare
  v_report text := '';
  v_pass int := 0;
  v_total int := 0;
  v_ver bigint;
  v_pub bigint;
  v_sec3d bigint;
  v_sec2a bigint;
  a bigint; b bigint; c bigint; d bigint; e bigint; x bigint;
  r jsonb;
begin
  select id into v_sec3d from sections where code = '3D';
  select id into v_sec2a from sections where code = '2A';
  if v_sec3d is null or v_sec2a is null then
    raise exception 'sections 3D and 2A must exist';
  end if;

  insert into timetable_versions (label, status, created_by)
    values ('TEST-PHASE-B-' || gen_random_uuid()::text, 'draft', 'test')
    returning id into v_ver;

  insert into timetable_entries (version_id, section_id, weekday, period_no, block_len, kind,
    subject_code, subject_name, faculty_code, room)
    values (v_ver, v_sec3d, 6, 1, 1, 'theory', 'T1', 'T1', 'AA', 'TEST RM A') returning id into a;
  insert into timetable_entries (version_id, section_id, weekday, period_no, block_len, kind,
    subject_code, subject_name, faculty_code, room)
    values (v_ver, v_sec3d, 6, 2, 1, 'theory', 'T2', 'T2', 'BB', 'TEST RM B') returning id into b;
  insert into timetable_entries (version_id, section_id, weekday, period_no, block_len, kind,
    subject_code, subject_name, faculty_code, room)
    values (v_ver, v_sec2a, 6, 3, 1, 'theory', 'T3', 'T3', 'ZZ', 'TEST RM C') returning id into c;
  insert into timetable_entries (version_id, section_id, weekday, period_no, block_len, kind,
    subject_code, subject_name, faculty_code, room)
    values (v_ver, v_sec3d, 6, 5, 1, 'theory', 'T4', 'T4', 'ZZ', 'TEST RM D') returning id into d;
  insert into timetable_entries (version_id, section_id, weekday, period_no, block_len, kind,
    subject_code, subject_name, faculty_code, room)
    values (v_ver, v_sec2a, 6, 7, 1, 'theory', 'T5', 'T5', 'YY', 'TEST RM A') returning id into e;

  -- T1: valid move succeeds and writes exactly one change-log row
  v_total := v_total + 1;
  begin
    r := apply_timetable_change(b, '{"period_no":2}', '{"period_no":4}', 'test');
    if (r->>'ok') = 'true' and (select count(*) from timetable_changes where entry_id = b) = 1 then
      v_pass := v_pass + 1; v_report := v_report || E'\nPASS T1 valid move';
    else
      v_report := v_report || E'\nFAIL T1 valid move: result ' || r::text;
    end if;
  exception when others then
    v_report := v_report || E'\nFAIL T1 valid move: ' || sqlerrm;
  end;

  -- T2: section clash (3D already has period 1)
  v_total := v_total + 1;
  begin
    r := apply_timetable_change(b, '{"period_no":4}', '{"period_no":1}', 'test');
    v_report := v_report || E'\nFAIL T2 section clash: no error raised';
  exception when others then
    if sqlerrm like '%CLASH%' then
      v_pass := v_pass + 1; v_report := v_report || E'\nPASS T2 section clash';
    else
      v_report := v_report || E'\nFAIL T2 section clash: ' || sqlerrm;
    end if;
  end;

  -- T3: faculty clash (ZZ teaches 2A in period 3)
  v_total := v_total + 1;
  begin
    r := apply_timetable_change(d, '{"period_no":5}', '{"period_no":3}', 'test');
    v_report := v_report || E'\nFAIL T3 faculty clash: no error raised';
  exception when others then
    if sqlerrm like '%CLASH%' then
      v_pass := v_pass + 1; v_report := v_report || E'\nPASS T3 faculty clash';
    else
      v_report := v_report || E'\nFAIL T3 faculty clash: ' || sqlerrm;
    end if;
  end;

  -- T4: room clash (TEST RM A is used by a in period 1)
  v_total := v_total + 1;
  begin
    r := apply_timetable_change(e, '{"period_no":7}', '{"period_no":1}', 'test');
    v_report := v_report || E'\nFAIL T4 room clash: no error raised';
  exception when others then
    if sqlerrm like '%CLASH%' then
      v_pass := v_pass + 1; v_report := v_report || E'\nPASS T4 room clash';
    else
      v_report := v_report || E'\nFAIL T4 room clash: ' || sqlerrm;
    end if;
  end;

  -- T5: stale edit is refused
  v_total := v_total + 1;
  begin
    r := apply_timetable_change(a, '{"subject_code":"WRONG"}', '{"room":"X"}', 'test');
    v_report := v_report || E'\nFAIL T5 stale edit: no error raised';
  exception when others then
    if sqlerrm like '%CONFLICT%' then
      v_pass := v_pass + 1; v_report := v_report || E'\nPASS T5 stale edit refused';
    else
      v_report := v_report || E'\nFAIL T5 stale edit: ' || sqlerrm;
    end if;
  end;

  -- T6: a field that is not editable is refused
  v_total := v_total + 1;
  begin
    r := apply_timetable_change(a, '{"period_no":1}', '{"version_id":999}', 'test');
    v_report := v_report || E'\nFAIL T6 non-editable field: no error raised';
  exception when others then
    if sqlerrm like '%not editable%' then
      v_pass := v_pass + 1; v_report := v_report || E'\nPASS T6 non-editable field refused';
    else
      v_report := v_report || E'\nFAIL T6 non-editable field: ' || sqlerrm;
    end if;
  end;

  -- T7: a published version cannot be edited
  insert into timetable_versions (label, status, created_by)
    values ('TEST-PHASE-B-PUB-' || gen_random_uuid()::text, 'draft', 'test')
    returning id into v_pub;
  insert into timetable_entries (version_id, section_id, weekday, period_no, block_len, kind,
    subject_code, subject_name, faculty_code, room)
    values (v_pub, v_sec3d, 6, 1, 1, 'theory', 'T6', 'T6', 'XX', 'TEST RM P') returning id into x;
  update timetable_versions set status = 'published' where id = v_pub;

  v_total := v_total + 1;
  begin
    r := apply_timetable_change(x, '{"period_no":1}', '{"room":"Q"}', 'test');
    v_report := v_report || E'\nFAIL T7 published version: no error raised';
  exception when others then
    if sqlerrm like '%not draft%' then
      v_pass := v_pass + 1; v_report := v_report || E'\nPASS T7 published version refused';
    else
      v_report := v_report || E'\nFAIL T7 published version: ' || sqlerrm;
    end if;
  end;

  raise exception 'PHASE B TEST REPORT (all test rows rolled back, nothing saved): % of % passed%',
    v_pass, v_total, v_report;
end $test$;
