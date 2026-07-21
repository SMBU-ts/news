#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并16篇新生成的摘要到 summaries/2026-07-21.json"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_PATH = ROOT / "summaries" / "2026-07-21.json"

summaries = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
before = len(summaries)

new_summaries = {
    "https://forum.jellyfin.org/t-project-leadership-changes": "Jellyfin项目创始人Joshua Boniface宣布离开团队,核心成员Anthony和Andrew也相继辞职。Joshua表示因严重倦怠和心理健康风险无法继续胜任,项目将交由现有团队接管,过渡友好,不会出现敌意分叉。Jellyfin已发展为拥有数百万用户的头部开源媒体服务器。",
    "https://www.ifanr.com/1672679": "蔚来旗下萤火虫品牌发布halo寻光系列首款车型「栖息地」,售价13.33万元,较发光版贵7500元。新车延续120kW电机和420km续航,升级集中在内外设计,采用「静谧绿」车漆和三重绿意座舱,灵感来自蓝绿色萤火虫。该系列将每年推出一款设计驱动的高端车型。",
    "https://www.ifanr.com/1672648": "OpenAI售价230美元的Codex Micro键盘首批售罄后,一位极客用Stream Deck+复刻了全部功能。通过自定义快捷键映射,可完成批准、拒绝、语音输入等八成操作,再配合第三方插件实现任务状态灯反馈。社区还涌现出用手柄、手机改造Codex控制台的开源项目。",
    "https://www.theverge.com/cs/features/937356/ai-data-center-gpu-environmental-impact": "The Verge探讨GPU能耗背后的道德与政治议题。单块Nvidia B200功耗达1200W,AI数据中心推高本地电价却难带来就业。但GPU无处不在,游戏GPU RTX 5090功耗575W,9200万台PS5同样耗电巨大,我们缺乏衡量何为「值得」的标准。",
    "https://www.theverge.com/news/968310/fcc-dji-drone-camera-ban-skyrover-xtra": "美国FCC首次拟动用追溯性禁令,封杀Skyrover无人机和Xtra相机等「DJI前台公司」产品。这些公司此前已获FCC批准进口销售,现拟禁止其继续进口、分销和营销。禁令不影响已购产品,目前正进行30天公众意见征集。",
    "https://www.qbitai.com/2026/07/456021.html": "在2026 WAIC上,上海仪电牵头的爱赛思OpenAI4S社区升级为「智爱赛思」社区,并发布科研专属Token Plan,推出学术体验包、科研标准包、实验攻坚包三档服务。社区集成Yi-Science-Evolving等AI4S模型,基于万卡级算力池为科研用户提供高峰不限流的智能科研服务。",
    "https://sspai.com/post/112582": "少数派社区速递第150期,派友热议磁吸配件话题,260人参与讨论,分享充电宝、支架、散热器等心得。作者还实测多款通气鼻贴和鼻内扩张器缓解鼻炎,推荐大行RUHM联名三折叠自行车DR-7C,售价4198元,折叠后可带入公共交通,适合城市休闲骑行。",
    "https://seekingalpha.com/news/4615736-bawag-group-ag-gaap-eps-of-328-core-revenue-of-5897m": "BAWAG Group AG公布财报,GAAP每股收益3.28欧元,核心收入5.897亿欧元。这家奥地利银行集团业绩表现稳健,反映欧洲银行业在当前经济环境下的运营状况。",
    "https://seekingalpha.com/news/4615744-danaher-non-gaap-eps-of-1_94-beats-by-0_09-revenue-of-6": "Danaher公布财报,Non-GAAP每股收益1.94美元,超出市场预期0.09美元,营收约60亿美元。这家生命科学与医疗诊断巨头业绩优于分析师预期,显示其核心业务持续增长。",
    "https://www.cnbc.com/2026/07/21/nebius-stock-nvidia-stake-neocloud.html": "Nebius股价盘前大涨约7%,因Nvidia在SEC文件中披露持有这家荷兰AI云计算公司9.3%股份。Nebius过去12个月股价累计上涨近250%,市值达460亿美元。此前Meta已与Nebius签署最高270亿美元的AI基础设施长期合作协议。",
    "https://seekingalpha.com/news/4615724-samsung-rises-after-korean-giant-forms-robotics-divi": "三星股价上涨,因这家韩国科技巨头宣布组建机器人业务部门。此举标志着三星正式进军机器人赛道,拓展除半导体、手机和家电之外的新增长领域,市场对其多元化战略反应积极。",
    "https://www.france24.com/en/spain-welcomes-back-its-world-cup-heroes": "西班牙热烈欢迎国家队世界杯冠军英雄凯旋。球队在夺得世界杯冠军后载誉归国,受到球迷和民众的热情迎接,举国欢庆这一历史性体育成就。",
    "https://www.france24.com/en/europe/20260721-russia-ukraine-war-first-half-of-2026-sees-sha": "据France 24报道,2026年上半年俄乌战争平民伤亡人数大幅上升。冲突持续升级导致更多平民卷入战火,人道主义危机加剧,引发国际社会对局势恶化的广泛关注。",
    "https://www.france24.com/en/video/20260721-we-re-living-in-fear-19-million-children-in-nig": "France 24报道称尼日利亚有1900万儿童失学,民众生活在恐惧之中。安全问题、贫困和教育基础设施缺失导致大量儿童无法接受教育,人道主义形势严峻。",
    "https://www.france24.com/en/the-uk-gets-new-government-as-prime-minister-vows-to-be-a-circ": "英国组建新政府,首相誓言成为「电路」般的领导者。新政府上台后承诺推动改革,应对英国面临的经济与社会挑战,开启政治新篇章。",
    "https://news.sky.com/story/family-of-six-killed-in-gaza-in-israeli-airstrike-13565495": "Sky News报道,加沙地带一家六口在以色列空袭中遇难。巴以冲突持续造成平民伤亡,这起悲剧再次引发国际社会对加沙人道主义危机的关注与忧虑。",
}

added = 0
for url, summary in new_summaries.items():
    if url not in summaries:
        added += 1
    summaries[url] = summary

SUMMARIES_PATH.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"摘要JSON: {before} -> {len(summaries)} 篇 (新增 {added})")
