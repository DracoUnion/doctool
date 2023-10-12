mv *.md D:\docs\love-course-2016-2019\docs\an-xiao-yao
$pwd = $(pwd).ToString()
cd D:\docs\love-course-2016-2019\
git pull
./update.sh
cd $pwd

$li = ls -n D:\docs\love-course-2016-2019\docs\an-xiao-yao

$exts = @('mp4', 'mp3', 'avi', 'mkv', 'mov', 'f4v', 'm4a', 'mpeg', 'flv', 'wav', 'wma', 'aac')

foreach($f in $li){
foreach($e in $exts){
rm $f.replace('.md', '.' + $e)
}
}
