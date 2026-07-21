#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并新生成的摘要到 summaries/2026-07-21.json"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_PATH = ROOT / "summaries" / "2026-07-21.json"

# 加载现有摘要
existing = {}
if SUMMARIES_PATH.exists():
    existing = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
    print(f"现有摘要: {len(existing)} 篇")

# 新摘要 - tech (19篇)
tech_summaries = {
    "https://news.ycombinator.com/item?id=48981136": "Bloomy是YC S26孵化的K-12 AI掌握式学习平台,由曾执教7年的Alex Southmayd创办。通过诊断学生技能差距、个性化学习路径和苏格拉底式AI辅导Bot,在马萨诸塞州试点中实现1.8倍预期学习增长,月费39美元起,旨在解决Bloom 2-sigma问题。",
    "https://vincentwoo.com/3d/grace_cathedral/": "Vincent Woo使用高斯泼溅(Gaussian Splatting)技术对旧金山格雷斯大教堂进行场景捕获与三维重建,基于PlayCanvas引擎打造沉浸式虚拟漫游体验,为历史建筑的数字化保护提供了新方案,并呼吁更多历史场景接入数字保存。",
    "https://www.tmtpost.com/8073569.html": "2026 WAIC收官,本届大会1100余家企业参展、4486项展品亮相创历史新高。AI从屏幕走向真实世界,宇树390万载人机甲、商汤机器人便利店日均400单、国产算力超节点集群集体亮相,中国正依托制造、场景、算力三重优势定义物理AI落地范式。",
    "https://nothings.org/gamedev/ssao/": "Sean Barrett通过真实照片像素级分析指出,游戏开发中广泛使用的屏幕空间环境光遮蔽(SSAO)存在明显缺陷:现实房间角落的暗化远比渲染效果轻微,强烈暗化多源于柔和阴影而非AO,视觉感知的暗化很大程度是马赫带错觉,呼吁开发者收集更准确数据改进SSAO实现。",
    "https://xenaproject.wordpress.com/2026/07/20/human-mathematicians-are-being-outcounterexampled": "Xena项目探讨人类数学家正被AI反例超越的现象,反映AI在数学证明与反例构造领域对人类数学家形成的挑战,引发关于数学研究未来走向的讨论。",
    "https://www.kimi.com/products/kimi-work": "月之暗面推出Kimi Work桌面AI Agent,深度连接本地文件、支持WebBridge浏览器自动化和24/7定时任务,内置Cron引擎可自动执行日报起草、数据处理等重复任务,预装A股、港股、美股数据源,定位为知识工作者的系统级数字员工。",
    "https://www.tokyodev.com/articles/vtubing-how-a-japanese-phenomenon-is-going-worldwide": "VTubing起源于日本,2023年日本市场规模达800亿日元同比增长153.8%。hololive和NIJISANJI两大事务所占全球收入40-45%,而海外市场则由独立创作者主导占观看量超50%。生成式AI在该领域被强烈抵制,未来将向3D技术和跨媒体IP扩展。",
    "https://blaizzy.github.io/nativ/": "Nativ是一款MIT开源的macOS本地AI运行应用,基于MLX-VLM优化Apple Silicon,支持Google、Cohere、Liquid AI等开源模型,提供语言、视觉、视频、代码、音频多模态能力,无需账号订阅,可连接Codex、Claude Code等编码工具作为本地端点。",
    "https://jelly-ui.com/": "Jelly UI是一个零依赖的Web Components组件库,将原生HTML表单控件与软体物理(soft-body physics)结合,提供按钮、输入框、滑块、开关等36个组件,内置暗色模式、RTL支持和WCAG AA色彩规范,通过script标签即可引入使用。",
    "https://exsitu.app/map": "Ex Situ是一个开源项目,构建流离失所文化遗产的空间索引地图,记录因战争、冲突等原因被迫迁移的文化文物与遗产的地理位置信息,为文化遗产保护与追踪提供可视化工具。",
    "https://www.armaangomes.com/blogs/doom/": "Armaan Gomes从逻辑门级别自研CPU并部署到FPGA,成功运行经典游戏DOOM。通过集成DDR3内存、设计ICache/DCache缓存、解决未初始化内存等Bug,将帧率从0.7 FPS提升至15-20 FPS,9秒演示视频获超200万播放量,未来目标30 FPS并移植Quake 2。",
    "https://www.instructables.com/A-Koi-Pond-Mosaic-Made-From-10-Pounds-of-3D-Printer-Waste": "Instructables用户将10磅(约4.5公斤)3D打印废料回收利用,制作成锦鲤池马赛克拼贴作品,展示了3D打印废弃物循环利用的创意手工艺实践。",
    "https://github.com/janestreet/incremental": "Jane Street开源的Incremental是OCaml增量计算库,受Umut Acar自调整计算研究启发,能高效响应输入变化更新复杂计算,适用于电子表格式大规模计算、GUI视图构建、派生数据同步等场景,最新版本v0.18于2026年7月发布。",
    "https://fzakaria.com/2026/07/20/linux-kernel-will-support-origin-sort-of": "Farid Zakaria向Linux内核提交补丁以支持Nix可重定位二进制文件的$ORIGIN变量。VFS维护者Christian Brauner在度假期间主动提出更通用的eBPF方案,通过binfmt_misc实现可编程解释器选择,新L标志支持PT_INTERP覆盖,补丁即将进入-next分支。",
    "https://qwen.ai/blog?id=qwen-image-3.0": "通义万相发布Qwen-Image-3.0第三代图像生成基础模型,核心关键词为\"实\",支持4.5k token输入生成报纸、分镜等复杂布局,可渲染10px小字与毛孔级细节,原生支持12种语言与网页游戏等UI界面,并接入互联网检索最新世界知识。",
    "https://sspai.com/post/112200": "作者在Surface Pro 5上安装Fedora与linux-surface内核,使这台老设备重获新生。GNOME的触控手势、工作区逻辑与Surface二合一形态契合,VS Code、Obsidian等开发写作工具迁移顺畅,虽有驱动稳定性和应用生态空缺,但已足够承载阅读、写作、开发等轻量工作流。",
    "https://36kr.com/p/3905042192189318": "36氪推出企业全情报小程序福利抽奖活动,用户进入小程序体验并订阅一家企业即可获得抽奖机会,一等奖为iPhone 17 Pro,旨在推广其AI驱动的企业工商、融资、舆情情报查询服务。",
    "https://www.theverge.com/tech/968375/sony-udio-lawsuit-songs-ai-copyright": "索尼音乐在纽约法院对AI音乐生成器Udio提起诉讼,指控其侵权超过3万首歌曲,涵盖碧昂丝、哈利·斯泰尔斯、猫王等艺人作品。索尼通过音频指纹技术在取证阶段识别出这些歌曲,但法官此前拒绝了将3万首加入原诉的动议,原诉范围仍限于333首作品。",
    "https://www.qbitai.com/2026/07/455993.html": "阿里健康医学AI平台\"氢离子\"先后与NEJM、JAMA、BMJ三大全球医学顶刊出版方达成内容合作,成为国内首个拥有三大顶刊全文内容授权的医学AI平台。医生可直接阅读文献全文并通过AI问答获取循证解答,引用可追溯原文。",
}

# 新摘要 - finance (15篇)
finance_summaries = {
    "https://seekingalpha.com/news/4615723-schindler-holding-gaap-eps-of-chf-249-revenue-of-chf-274b": "瑞士电梯制造商迅达集团(Schindler Holding)公布最新财报,GAAP每股收益为2.49瑞郎,营收达27.4亿瑞郎。业绩反映公司在全球电梯和自动扶梯市场的稳健表现,为投资者评估全球建筑和基建需求提供了重要参考。",
    "https://www.cnbc.com/2026/07/21/us-iran-war-trump-hormuz-houthis.html": "美军连续第十个夜晚对伊朗发动打击,伊朗在霍尔木兹海峡袭击油轮,也门胡塞武装宣布对沙特实施海上禁运。中东冲突威胁全球约20%的石油运输,Rystad Energy警告若停火未达成且海峡持续封锁,油价可能大幅反弹,约250万桶/日的沙特石油面临风险。",
    "https://seekingalpha.com/news/4615706-london-stock-exchange-plans-to-launch-245-trading-next-year": "伦敦证券交易所计划于明年推出每周5天、每天24小时(24/5)的延长交易机制。此举旨在提升伦敦市场的全球竞争力,吸引更多国际投资者,与纽约等市场争夺交易流量,标志欧洲传统交易模式的重大变革。",
    "https://seekingalpha.com/news/4615725-mercantile-bank-non-gaap-eps-of-153-beats-by-020-revenue-misses": "Mercantile Bank Corporation公布二季度业绩:Non-GAAP每股收益1.53美元,超出预期0.20美元;营收6880万美元,同比增长12.9%。资产回报率1.5%,股本回报率14.0%。截至6月30日每股有形账面价值38.42美元,总存款53亿美元,盈利表现强劲。",
    "https://seekingalpha.com/news/4615720-tsmc-to-raise-chip-manufacturing-prices-by-up-to-10-in-2027": "台积电(TSMC)计划在2027年将芯片制造价格上调最高10%。此举反映先进制程产能紧张、制造成本上升以及对AI和高性能计算需求的强劲预期。作为全球最大代工芯片制造商,台积电涨价将影响整个半导体产业链,对英伟达、AMD等客户构成成本压力。",
    "https://seekingalpha.com/news/4615653-ant-group-affiliate-ant-international-raises-12b-to-boost-global-treasury": "蚂蚁集团关联公司蚂蚁国际(Ant International)筹集12亿美元资金,用于加强全球资金管理业务。此举显示蚂蚁系在跨境支付和财资管理领域的扩张意图,旨在服务全球企业的国际资金调配需求,延续蚂蚁集团的国际化战略。",
    "https://seekingalpha.com/news/4615722-biggest-stock-movers-tuesday-nbis-zion-and-more": "周二盘前美股期货小幅走高,投资者在中东摩擦和AI支出热潮担忧中寻找方向。主要个股动向:Nebius(NBIS)涨约6%领涨;ZION、台积电(TSM)、CCK、MGY等也受到关注。中东局势和AI投资主题持续影响市场情绪,资金在防御与成长板块之间轮动。",
    "https://www.cnbc.com/2026/07/21/andy-burnham-john-healey-chancellor-gilts-jamie-dimon.html": "Andy Burnham就任英国十年内第七位首相后,任命John Healey为财政大臣。新政府宣布将家庭电费增值税从5%降至0%,预计耗资8.5亿英镑。国债收益率小幅回落,但市场仍警惕财政风险。摩根大通CEO戴蒙呼吁新政府聚焦经济增长。",
    "https://www.cnbc.com/2026/07/21/andy-burnham-uk-prime-minister-vat.html": "英国新首相Burnham上任后推出首个重大政策:取消家庭电费增值税(VAT),每户年均节省约45英镑。但文章警告,财政与经济稳定对英国家庭更为重要。英国国债收益率较意大利BTP高出逾100个基点,推高了抵押贷款成本,Burnham真正考验在于能否恢复英国财政信誉。",
    "https://seekingalpha.com/news/4615713-anthropics-15b-settlement-in-authors-copyright-lawsuit": "AI公司Anthropic同意以15亿美元和解作家版权集体诉讼。原告作家指控Anthropic未经授权使用其著作训练Claude大语言模型。这一和解金额创下AI训练数据版权纠纷的最高纪录,为行业树立重要先例,可能影响OpenAI、Meta等其他AI公司面临的类似诉讼。",
    "https://www.cnbc.com/2026/07/21/boeing-airbus-narrow-body-planes-deliveries-737-max-a321.html": "波音与空客正准备在窄体客机市场展开新一轮竞争,焦点集中在737 MAX与A321系列机型。两大制造商在交付量、产能提升和订单争夺上角力,以满足全球航司对单通道客机的强劲需求。窄体机市场是民用航空利润最丰厚的细分领域,竞争格局将影响双方未来十年的市场份额。",
    "https://www.cnbc.com/2026/07/21/treasury-yields-bonds-iran-us-politics.html": "周二美债收益率全线小幅走低,投资者权衡中东局势升级与斡旋停火的努力。10年期美债收益率报4.594%基本持平,2年期升至4.198%,30年期报5.118%。BMO指出,尽管中东局势升级,国债市场保持相对稳定,停火提案抑制了油价。7、8月通胀数据将是判断能源通胀是否见顶的关键。",
    "https://www.cnbc.com/2026/07/21/abu-dhabi-gas-project-uae-energy-supply.html": "阿布扎比国家石油公司批准62亿美元开发Umm Shaif海上油气田,预计2030年新增日产量超6亿立方英尺天然气,相当于阿联酋当前日消费量的近10%。该项目与道达尔、埃尼、中石油合作开发,旨在强化阿联酋能源安全并扩大LNG出口,目标2035年LNG产能达4700万吨/年。",
    "https://www.cnbc.com/2026/07/21/india-sbi-market-debut-billion-ipo.html": "印度最大资管公司SBI Funds Management在10亿美元IPO后上市首日仅溢价7%,表现平淡。该IPO获机构投资者热烈追捧,超额认购41.6倍,认购金额达307亿美元。公司管理资产29.5万亿卢比(3950亿美元)。伊朗战争推高能源价格冲击印度经济,Sensex指数年内跌超9%。",
    "https://www.cnbc.com/2026/07/21/samsung-electronics-sets-up-robotics-unit-amid-push-into-ai.html": "三星电子成立机器人业务部门,加快向人工智能领域布局,推动股价上涨。此举显示这家韩国科技巨头在半导体之外寻求新增长引擎,瞄准机器人和AI融合的产业机遇,将与日本、中国及美国竞争对手在智能机器人和自动化领域展开较量。",
}

# 新摘要 - world (17篇)
world_summaries = {
    "https://www.france24.com/en/protests-erupt-in-bologna-after-moroccan-man-dies-under-police": "意大利博洛尼亚一名摩洛哥男子在警方拘留期间死亡,引发当地民众抗议活动。事件加剧了移民社区与执法部门之间的紧张关系,示威者要求对涉事警察进行问责,并呼吁彻查事件真相。",
    "https://www.france24.com/en/europe/20260721-demonstrations-break-out-in-bologna-after-moroccan-man-dies": "意大利博洛尼亚一名摩洛哥男子死亡事件持续发酵,引发大规模示威活动。抗议者与警方发生冲突,事件引发对警察执法和移民待遇的广泛讨论,当局面临彻查事件的压力。",
    "https://www.france24.com/en/tv-shows/sports/20260721-world-cup-2026-spain-return-to-madrid-in-triumph": "西班牙国家足球队在2026年世界杯决赛加时赛1-0击败阿根廷夺冠后返回马德里,受到热烈欢迎。超过100万球迷参与庆祝游行,球队在西贝莱斯广场举行盛大庆典,这是西班牙自2010年以来再次夺得世界杯冠军。",
    "https://www.npr.org/2026/07/21/nx-s1-5901832/spain-world-cup-champions-return-home": "西班牙队夺得2026年世界杯冠军后返回马德里,约180万球迷沿街欢迎。球员会见国王费利佩六世和首相桑切斯后,乘敞篷巴士游行至西贝莱斯广场举行庆典。费兰·托雷斯加时赛打入制胜球,西班牙成为首个同时持有男女足世界杯的国家。",
    "https://news.sky.com/story/anti-police-protests-erupt-in-bologna-after-moroccan-man-dies": "意大利博洛尼亚一名摩洛哥男子在警方行动中死亡,引发反警察暴力抗议活动。示威者走上街头表达对执法部门的不满,事件再次引发关于警察执法方式和移民权益的讨论。",
    "https://www.france24.com/en/middle-east-war-stuck-in-cycle-of-enhanced-risk-as-us-strikes-iran": "美国对伊朗发动打击后,中东战争陷入\"风险升级循环\"。分析人士警告地区冲突可能进一步扩大,各方紧张局势加剧,国际社会对局势失控表示担忧,呼吁通过外交途径缓解危机。",
    "https://www.france24.com/en/europe/20260721-uk-prime-minister-andy-burnham-unveils-new-government": "英国新任首相安迪·伯纳姆公布新政府内阁成员。伯纳姆接替辞职的基尔·斯塔默成为英国十年内第七位首相,承诺推出生活成本援助措施、终结露宿街头现象,并废除数字身份证计划。",
    "https://www.france24.com/en/mostly-symbolic-does-aoun-s-white-house-visit-signal": "黎巴嫩总统奥恩访问白宫会晤特朗普,分析人士认为此次访问\"主要是象征性的\"。双方讨论了中东局势和以色列撤军问题,但实质性成果有限,反映黎巴嫩在地区事务中的复杂处境。",
    "https://www.france24.com/en/asia-pacific/20260721-beijing-summons-philippine-ambassador": "中国就南海争议海域冲突事件召见菲律宾驻华大使。双方在争议水域发生对峙,北京表达强烈不满,地区紧张局势再度升温,引发国际社会对南海局势的关注。",
    "https://www.npr.org/2026/07/21/nx-s1-5901828/powerball-begin-united-kingdom": "美国强力球彩票将于周二起在英国发售,这是该彩票首次在美国以外地区销售。英国玩家可争夺与美国玩家相同的巨额头奖,周三晚抽奖将首次对英国开放。中奖概率为2.922亿分之一,票价2美元。",
    "https://www.npr.org/2026/07/19/nx-s1-5895993/andy-burnham-prime-minister-keir-starmer": "安迪·伯纳姆接替基尔·斯塔默成为英国新任首相,是英国十年内第七位首相。伯纳姆曾任大曼彻斯特市长,承诺推出生活成本援助、终结露宿街头,已与特朗普通话讨论防务,并与泽连斯基通电话表达对乌克兰的坚定支持。",
    "https://www.france24.com/en/middle-east/20260721-live-lebanon-s-aoun-to-meet-trump": "伊朗革命卫队宣布袭击了美国雷达设施,中东紧张局势急剧升级。与此同时,黎巴嫩总统奥恩将晤特朗普讨论以色列撤军问题,地区冲突持续发酵,各方关切冲突进一步扩大的风险。",
    "https://news.sky.com/story/russian-warship-carries-out-live-fire-weapons-exercise": "俄罗斯军舰在距离某地46海里处进行实弹军事演习。此次演习引发周边国家对地区安全局势的关注,被解读为莫斯科展示军事存在和力量的举措,加剧了地缘政治紧张。",
    "https://www.foxnews.com/world/nicaragua-ortega-ends-elections": "尼加拉瓜总统奥尔特加宣布该国将\"永远不再\"举行选举,进一步关闭反对派挑战政府的途径。奥尔特加与妻子穆里略通过宪法改革巩固权力,控制立法、司法和选举机构,美国已制裁2000多名尼加拉瓜官员。",
    "https://news.sky.com/story/how-the-world-cup-was-won-spains-victory-in-charts": "数据图表回顾西班牙队夺得2026年世界杯冠军的历程。西班牙在决赛中1-0击败阿根廷,时隔16年再次捧起大力神杯,数据显示西班牙在控球率、传球成功率等关键指标上均表现出色。",
    "https://www.france24.com/en/middle-east/20260721-lebanon-s-aoun-to-press-trump-for-israeli-troop": "黎巴嫩总统奥恩将敦促特朗普推动以色列从黎巴嫩撤军。双方会晤聚焦中东局势和黎以关系,奥恩寻求美方支持以确保以色列遵守停火协议并撤出军队,维护黎巴嫩主权。",
    "https://www.france24.com/en/france/20260721-french-lawmakers-expected-to-pass-social-media-ban": "法国议员预计将通过一项针对儿童的社交媒体禁令。该法案旨在保护未成年人免受社交媒体负面影响,包括网络欺凌和有害内容,标志着法国在数字保护立法方面迈出重要一步。",
}

# 合并所有新摘要
new_summaries = {}
new_summaries.update(tech_summaries)
new_summaries.update(finance_summaries)
new_summaries.update(world_summaries)

print(f"新摘要: {len(new_summaries)} 篇 (tech={len(tech_summaries)}, finance={len(finance_summaries)}, world={len(world_summaries)})")

# 合并到现有摘要
added = 0
updated = 0
for url, summary in new_summaries.items():
    if url in existing:
        updated += 1
    else:
        added += 1
    existing[url] = summary

print(f"合并结果: 新增 {added} 篇, 更新 {updated} 篇, 总计 {len(existing)} 篇")

# 写回文件
SUMMARIES_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已写入: {SUMMARIES_PATH}")
