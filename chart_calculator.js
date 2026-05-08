/**
 * 紫微斗数命盘计算器
 * 用法: node chart_calculator.js "2000-8-16" 2 "男" false
 * 参数: 出生日期(YYYY-M-D) 时辰索引(0-11) 性别 是否农历
 * 输出: JSON 命盘数据
 */

const { astro } = require('iztro');

const [,, birthday, timeIdx, gender, isLunar] = process.argv;

if (!birthday || timeIdx === undefined || !gender) {
  console.error('用法: node chart_calculator.js <YYYY-M-D> <时辰0-11> <男|女> [lunar]');
  console.error('时辰: 0=子时,1=丑,2=寅,3=卯,4=辰,5=巳,6=午,7=未,8=申,9=酉,10=戌,11=亥');
  process.exit(1);
}

try {
  const options = {
    birthday: birthday.trim(),
    birthTime: parseInt(timeIdx),
    gender: gender.trim(),
    isLeapMonth: false,
    language: 'zh-CN',
  };

  let astrolabe;
  if (isLunar === 'true' || isLunar === 'lunar') {
    // 农历排盘: byLunar(birthday, timeIdx, gender, isLeapMonth, fixLeap, lang)
    astrolabe = astro.byLunar(birthday.trim(), parseInt(timeIdx), gender.trim(), false, true, 'zh-CN');
  } else {
    astrolabe = astro.bySolar(birthday.trim(), parseInt(timeIdx), gender.trim(), false, 'zh-CN');
  }

  // 提取晴晰的命盘数据
  const output = {
    // 基本信息
    基本信息: {
      性别: astrolabe.gender,
      阳历: astrolabe.solarDate,
      农历: astrolabe.lunarDate,
      生肖: astrolabe.chineseDate?.split(' ')?.[0] || '',
      时辰: ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'][parseInt(timeIdx)] + '时',
      四柱: astrolabe.chineseDate || '',
    },

    // 十二宫
    命盘: astrolabe.palaces.map(p => ({
      宫位: p.name,
      天干: p.heavenlyStem,
      地支: p.earthlyBranch,
      身宫: p.isBodyPalace || false,
      主星: (p.majorStars || []).filter(s => s).map(s => typeof s === 'object' ? (s.name || s.type || '') : s).filter(Boolean).join('、') || '无',
      辅星: (p.minorStars || []).filter(s => s).map(s => typeof s === 'object' ? (s.name || s.type || '') : s).filter(Boolean).join('、') || '无',
      四化: (p.mutagens || []).filter(m => m).map(m => `${m.star||''}${m.type||''}`).join('、') || '',
    })),

    // 五行局
    五行局: astrolabe?.fiveElementsClass || '',
  };

  // 运限
  if (astrolabe?.getHoroscope) {
    try {
      const currentYear = new Date().getFullYear();
      const liunian = astrolabe.getHoroscope(String(currentYear));
      if (liunian && liunian.length > 0) {
        output.流年 = liunian.map(p => ({
          宫位: p.name,
          流年主星: (p.majorStars || []).filter(s => s).map(s => typeof s === 'object' ? (s.name || s.type || '') : s).filter(Boolean).join('、') || '',
          四化: (p.mutagens || []).filter(m => m).map(m => `${m.star||''}${m.type||''}`).join('、') || '',
        }));
      }
    } catch (e) {
      // 流年计算可能不支持某些版本
    }
  }

  process.stdout.write(JSON.stringify(output, null, 2));
} catch (err) {
  console.error('排盘失败:', err.message);
  process.exit(1);
}
