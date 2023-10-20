
function mv_md_rm_aud($aud_dir, $md_dir){
	mv "$aud_dir\*.md" $md_dir
	$pwd = $(pwd).ToString()
	cd $md_dir\..\..
	git pull
	./update.sh
	cd $pwd
	$exts = @('mp4', 'mp3', 'avi', 'mkv', 'mov', 'f4v', 'm4a', 'mpeg', 'flv', 'wav', 'wma', 'aac')

	$li = ls -n $md_dir
	foreach($f in $li){
		foreach($e in $exts){
			$nf = $f.replace('.md', '.' + $e)
			rm $aud_dir\$nf
		}
	}
}

for(;;){
	mv_md_rm_aud D:\bili\19-5-moka  D:\docs\love-course-2016-2019\docs\mo-ka
	mv_md_rm_aud D:\bili\19-8-wuya  D:\docs\love-course-2016-2019\docs\wu-ya
	sleep 600
}