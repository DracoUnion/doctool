$li=@(@('A Common-Sense Guide to Data Structures and Algorithms in JavaScript.epub', 'cmss-gd-dsal-js'),
@('Advanced JavaScript Unleashed.epub', 'adv-ks-unlsh'),
@('Inside the Code_ Unraveling How Languages Like C, C++, Java, JavaScript, and Python Work.epub', 'insd-cd'),
@('JavaScript Essentials For Dummies.epub', 'js-ess-dmm'),
@('Learn coding with Python and JavaScript.epub', 'lrn-cd-py-js'),
@('MASTERING REACT JS AND JAVASCRIPT MASTERY.epub', 'ms-rct-js'),
@('Node.Js And Javascript Programming Made Simple.epub', 'node-js-proh-mdsim'),
@('Text Processing with JavaScript.epub', 'txt-proc-js'),
@('The Golden Book of JavaScript.epub', 'gldn-bk-js'),
@('Vue.js Essentials.epub', 'vue-ess'))

$proj = 'd:/docs/trans-js'
md $proj/totrans
md $proj/data

foreach($it in $li){
	$fname = $it[0]
	$doc = $it[1]
	md tmp
	md $proj/docs/$doc/img
	epub-tool ext-pics $fname -o $proj/docs/$doc/img -p "${doc}_"
	epub-tool ext-htmls $fname -o tmp -p "${doc}_"
	md-tool tomd tmp -l js
	md-tool ext-pre tmp
	md-tool mk-totrans tmp
	mv tmp/*.yaml $proj/totrans
	mv tmp/*.json $proj/totrans
	rm -r tmp
	
}