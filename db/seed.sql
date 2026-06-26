-- Sample meeting transcripts for local testing

INSERT INTO channels (channel_id, name) VALUES
    ('UC_local_city', 'Local City Government')
ON CONFLICT (channel_id) DO NOTHING;

INSERT INTO videos (video_id, channel_id, title, published_at, is_meeting, meeting_type) VALUES
    (
        'sample_city_council_001',
        (SELECT id FROM channels WHERE channel_id = 'UC_local_city'),
        'City Council Meeting - June 10, 2025',
        NOW() - INTERVAL '3 days',
        TRUE,
        'city_council'
    ),
    (
        'sample_school_board_001',
        (SELECT id FROM channels WHERE channel_id = 'UC_local_city'),
        'School Board Meeting - June 12, 2025',
        NOW() - INTERVAL '1 day',
        TRUE,
        'school_board'
    )
ON CONFLICT (video_id) DO NOTHING;

INSERT INTO transcripts (video_id, language, full_text, word_count) VALUES
    (
        (SELECT id FROM videos WHERE video_id = 'sample_city_council_001'),
        'en',
        'Mayor Johnson called the meeting to order at 7:00 PM. Agenda item one: approval of the downtown revitalization bond measure for 12 million dollars. Councilmember Rivera raised concerns about displacement of small businesses on Main Street. The planning director presented traffic impact studies showing a 15 percent increase in congestion without mitigation. Public comment included testimony from the Main Street Merchants Association opposing the current design. Agenda item two: zoning variance for the proposed mixed-use development at 400 Oak Avenue. The developer requested increased height limits from four to six stories. Environmental advocates cited wetland proximity and stormwater runoff risks. The council voted 4-3 to table the variance pending an independent environmental review. Agenda item three: police department budget review. Chief Martinez requested funding for body cameras and community liaison officers. Several residents spoke about response times in the north side neighborhood averaging 18 minutes. The finance committee will revisit the budget at next month''s meeting.',
        165
    ),
    (
        (SELECT id FROM videos WHERE video_id = 'sample_school_board_001'),
        'en',
        'Board President Chen opened the school board meeting. First topic: superintendent search update. The search firm presented three finalist candidates with backgrounds in urban district turnaround. Parents from Lincoln Elementary asked about each candidate''s experience with special education programs. Second topic: proposed 2026 budget with a 4.2 percent increase driven by rising transportation and food service costs. The business administrator explained that state aid projections remain flat while enrollment grew by 180 students. Third topic: curriculum adoption for middle school science aligned with new state standards. Teachers union representatives requested additional professional development days before rollout. Fourth topic: facilities plan for roof repairs at Washington High and HVAC upgrades at two elementary schools totaling 3.1 million dollars. A bond referendum may be placed on the November ballot. Public comment period lasted 45 minutes with most speakers supporting the facilities plan.',
        158
    )
ON CONFLICT (video_id, language) DO NOTHING;
