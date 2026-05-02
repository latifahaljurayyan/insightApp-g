-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
-- Host: 127.0.0.1
-- Generation Time: Mar 18, 2026 at 09:10 AM
-- Server version: 9.1.0
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


-- Database: `appinsight`

-- Table structure for table `admin`

CREATE TABLE `admin` (
  `admin_id` int NOT NULL AUTO_INCREMENT,
  `email` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `password` varchar(255) COLLATE utf8mb4_general_ci NOT NULL,
   PRIMARY KEY (`admin_id`),
   UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `admin` (`email`, `password`) VALUES
('Adminappinsight@gmail.com', '123456');

-- --------------------------------------------------------

-- Table structure for table `user`

CREATE TABLE `user` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `first_name` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `last_name` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `email` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `password` varchar(255) COLLATE utf8mb4_general_ci NOT NULL,
  `gender` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `dob` date DEFAULT NULL,
  `phone` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `status` varchar(20) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'active',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

-- Table structure for table `faq`

CREATE TABLE `faq` (
  `faq_id` int NOT NULL AUTO_INCREMENT,
  `question` text COLLATE utf8mb4_general_ci NOT NULL,
  `answer` text COLLATE utf8mb4_general_ci NOT NULL,
  `updated_at` date NOT NULL,
    PRIMARY KEY (`faq_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------


-- Table structure for table `file`


CREATE TABLE `file` (
   `file_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `app_name` varchar(40) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `file_path` varchar(200) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `model_version` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `uploaded_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`file_id`),
  KEY `user_id` (`user_id`),
 CONSTRAINT `file_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------


-- Table structure for table `review`


CREATE TABLE `review` (
  `review_number` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `review_text` text COLLATE utf8mb4_general_ci,
  `rating` float DEFAULT NULL,
  `sentiment_label` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`review_number`),
  KEY `file_id` (`file_id`), 
  CONSTRAINT `review_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `file` (`file_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------


-- Table structure for table `single_analysis` (تحليل ملف واحد)

CREATE TABLE `single_analysis` (
  `result_number` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `positive_percent` float DEFAULT NULL,
  `negative_percent` float DEFAULT NULL,
  `neutral_percent` float DEFAULT NULL,
  `average_rating` float DEFAULT NULL,
  `top_positive_features` text COLLATE utf8mb4_general_ci,
  `top_negative_features` text COLLATE utf8mb4_general_ci,
  `cached_result` mediumtext COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`result_number`),
  CONSTRAINT `single_analysis_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `file` (`file_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

-- Table structure for table `comparison_analysis` (مقارنة ملفين)

CREATE TABLE `comparison_analysis` (
  `result_number` int NOT NULL AUTO_INCREMENT,
  `file1_id` int NOT NULL,
  `file2_id` int NOT NULL,
  `file1_positive_percent` float DEFAULT NULL,
  `file1_negative_percent` float DEFAULT NULL,
  `file1_neutral_percent` float DEFAULT NULL,
  `file1_average_rating` float DEFAULT NULL,
  `file1_top_positive_features` text COLLATE utf8mb4_general_ci,
  `file1_top_negative_features` text COLLATE utf8mb4_general_ci,
  `file2_positive_percent` float DEFAULT NULL,
  `file2_negative_percent` float DEFAULT NULL,
  `file2_neutral_percent` float DEFAULT NULL,
  `file2_average_rating` float DEFAULT NULL,
  `file2_top_positive_features` text COLLATE utf8mb4_general_ci,
  `file2_top_negative_features` text COLLATE utf8mb4_general_ci,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`result_number`),
  CONSTRAINT `comparison_analysis_ibfk_1` FOREIGN KEY (`file1_id`) REFERENCES `file` (`file_id`),
  CONSTRAINT `comparison_analysis_ibfk_2` FOREIGN KEY (`file2_id`) REFERENCES `file` (`file_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;



COMMIT;

